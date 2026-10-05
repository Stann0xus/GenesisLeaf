"""Compare-pack pairing engine: match MINE entries to OTHER entries.

Pure data in, pure data out - no Tk - so the comparator can run it on a
worker thread.  See ui/app/compare.py for the table built from the result.

Part of GenesisLeaf - see docs/ARCHITECTURE.md.
"""

import bisect
import difflib
import re

from genesisleaf.core.textfix import ascii_fold

FUZZY_MIN = 0.8     # weakest similarity offered as a candidate

_NORM_RE = re.compile(r"[^0-9a-z぀-ヿ一-鿿]+")


def norm(s):
    """Comparison form of a field: folded, lowercased, and stripped of
    everything that is not a letter, digit or CJK character - so
    "Hello!" == "hello" and "Sao Paulo" == "saopaulo"."""
    return _NORM_RE.sub("", ascii_fold(s or "").lower())


def snapshot(flat):
    """`[(sec, uuid, key, source, context)]` for a pack's flat list - the only
    fields the matcher reads, copied so a worker thread never touches the
    live entry dicts."""
    return [(sec, e.get("uuid", ""), e.get("key", ""), e.get("source", ""),
             e.get("context", "")) for sec, e in flat]


def match(mine, other, cancelled=None):
    """Pair every MINE entry with the best free OTHER entry (or none).

    `mine` / `other` are `snapshot()` lists.  Returns `(pairs, unused)`:
    `pairs` is one `(mine_index, other_index_or_None, level, evidence)` per
    MINE entry in order, `unused` the OTHER indices nobody claimed.

    The indexes keep the common evidence cheap: uuid, exact key, exact
    source, normalised source, normalised context.  Fuzzy source comparison
    only ever runs inside ONE context bucket, so a look-alike line from
    elsewhere in the game is never offered as a match, and each OTHER entry
    is used at most once.

    The fuzzy pass is what used to make two unrelated packs (say English vs
    romaji Japanese, where almost nothing pairs by key or source) take
    minutes: every MINE line ran SequenceMatcher against its whole context
    bucket, re-normalising each candidate every time.  Now each bucket is
    sorted by length - a ratio >= 0.8 needs the shorter string to be at
    least 2/3 of the longer one, so only that window is visited - and the
    cheap upper bounds (real_quick_ratio, quick_ratio) reject a candidate
    before the full ratio is computed.  The result is identical.

    `cancelled()` (optional) is polled now and then; when it returns True the
    match stops early and returns None."""
    used = [False] * len(other)
    by_uuid, by_key, by_src, by_snorm, by_ctx = {}, {}, {}, {}, {}
    o_snorm = []
    for oi, (_sec, uu, key, src, ctx) in enumerate(other):
        if uu:
            by_uuid.setdefault(uu, []).append(oi)
        if key:
            by_key.setdefault(key, []).append(oi)
        if src:
            by_src.setdefault(src, []).append(oi)
        sn = norm(src)
        o_snorm.append(sn)
        if sn:
            by_snorm.setdefault(sn, []).append(oi)
            cn = norm(ctx)
            if cn:
                by_ctx.setdefault(cn, []).append((len(sn), oi))
    buckets = {cn: _Bucket(items, o_snorm) for cn, items in by_ctx.items()}

    def first_free(idxs):
        for oi in idxs:
            if not used[oi]:
                return oi
        return None

    sm = difflib.SequenceMatcher(None)
    pairs = []
    for i, (sec, uu, key, src, ctx) in enumerate(mine):
        if cancelled is not None and not i % 512 and cancelled():
            return None
        snorm = norm(src)
        oi = None
        level = "none"
        ev = []
        if uu and uu in by_uuid:
            got = first_free(by_uuid[uu])
            if got is not None:
                oi, level, ev = got, "direct", ["same uuid"]
        if oi is None and key and key in by_key:
            got = first_free(by_key[key])
            if got is not None:
                oi, level, ev = got, "direct", ["same key"]
        if oi is None and src and src in by_src:
            # a byte-identical source is strong evidence on its own; the
            # same section upgrades it to beyond-question
            got = first_free(o for o in by_src[src] if other[o][0] == sec)
            if got is not None:
                oi, level, ev = got, "direct", ["source matches",
                                                "same section"]
            else:
                got = first_free(by_src[src])
                if got is not None:
                    oi, level = got, "strong"
                    ev = ["source matches", "section renamed"]
        if oi is None and snorm and snorm in by_snorm:
            got = first_free(by_snorm[snorm])
            if got is not None:
                oi = got
                if other[got][0] == sec:
                    level = "strong"
                    ev = ["same source (ignoring case/spaces/punctuation)",
                          "same section"]
                else:
                    level = "weak"
                    ev = ["same source (ignoring case/spaces/punctuation)",
                          "sections renamed it"]
        if oi is None and snorm:
            cn = norm(ctx)
            bucket = buckets.get(cn) if cn else None
            if bucket is not None:
                best, ratio = _best_fuzzy(sm, snorm, bucket, used)
                if best is not None and ratio >= FUZZY_MIN:
                    oi, level = best, "weak"
                    ev = ["same context",
                          "source %d%% similar" % round(ratio * 100)]
        if oi is not None:
            used[oi] = True
        pairs.append((i, oi, level, ev))
    unused = [oi for oi in range(len(other)) if not used[oi]]
    return pairs, unused


class _Bucket:
    """One context bucket: its OTHER entries sorted by normalised-source
    length, plus their character counts for the quick-ratio bound (a numpy
    count matrix when numpy is installed, else one dict per entry).  The
    counts are built on first use - most buckets never need them."""

    def __init__(self, items, o_snorm):
        items.sort()
        self.lens = [n for n, _ in items]
        self.idxs = [oi for _, oi in items]
        self._o_snorm = o_snorm
        self._counts = None
        self._mat = None

    def candidates(self, snorm, lo, hi):
        """OTHER indices in [lo, hi) whose quick ratio against `snorm` can
        reach FUZZY_MIN, in bucket order."""
        if _np is not None:
            return self._candidates_np(snorm, lo, hi)
        if self._counts is None:
            self._counts = [_char_counts(self._o_snorm[oi])
                            for oi in self.idxs]
        q = _char_counts(snorm)
        n = len(snorm)
        out = []
        for k in range(lo, hi):
            inter = 0
            for ch, c in self._counts[k].items():
                qc = q.get(ch)
                if qc:
                    inter += c if c < qc else qc
            if 2.0 * inter >= FUZZY_MIN * (n + self.lens[k]):
                out.append(self.idxs[k])
        return out

    def _candidates_np(self, snorm, lo, hi):
        if self._mat is None:
            alpha = {}
            for oi in self.idxs:
                for ch in self._o_snorm[oi]:
                    alpha.setdefault(ch, len(alpha))
            mat = _np.zeros((len(self.idxs), max(1, len(alpha))),
                            dtype=_np.int32)
            for k, oi in enumerate(self.idxs):
                for ch, c in _char_counts(self._o_snorm[oi]).items():
                    mat[k, alpha[ch]] = c
            self._alpha = alpha
            self._mat = mat
            self._lens = _np.asarray(self.lens, dtype=_np.float64)
        # only the query's own characters can add to the intersection, so
        # the bound needs just their columns (a bucket's alphabet can run to
        # hundreds of kana / kanji)
        cols, qv = [], []
        for ch, c in _char_counts(snorm).items():
            col = self._alpha.get(ch)
            if col is not None:
                cols.append(col)
                qv.append(c)
        if not cols:
            return []
        sub = self._mat[lo:hi, cols]
        inter = _np.minimum(sub, _np.asarray(qv, dtype=_np.int32)).sum(axis=1)
        ok = 2.0 * inter >= FUZZY_MIN * (len(snorm) + self._lens[lo:hi])
        return [self.idxs[lo + k] for k in _np.flatnonzero(ok).tolist()]


try:                                  # optional: only speeds up _Bucket
    import numpy as _np
except Exception:                     # noqa: BLE001
    _np = None


def _char_counts(s):
    d = {}
    for ch in s:
        d[ch] = d.get(ch, 0) + 1
    return d


def _best_fuzzy(sm, snorm, bucket, used):
    """Most similar free entry of one context bucket: `(index, ratio)`.

    Ties go to the lowest OTHER index, as a plain scan in pack order would.
    Only candidates whose length allows a ratio >= FUZZY_MIN are visited
    (2*m/(a+b) >= 0.8 needs min(a, b) >= 2/3 * max(a, b)), and of those only
    the ones whose quick ratio (difflib's multiset upper bound) gets there
    reach the real SequenceMatcher."""
    n = len(snorm)
    lo = bisect.bisect_left(bucket.lens, (2 * n + 2) // 3)
    hi = bisect.bisect_right(bucket.lens, (3 * n) // 2)
    if lo >= hi:
        return None, 0.0
    # MINE stays `a` and OTHER `b`, as the original per-pair matcher had
    # them: the ratio is not quite symmetric (b's junk heuristic)
    sm.set_seq1(snorm)
    best, ratio = None, 0.0
    for o_i in bucket.candidates(snorm, lo, hi):
        if used[o_i]:
            continue
        sm.set_seq2(bucket._o_snorm[o_i])
        r = sm.ratio()
        if r < FUZZY_MIN:
            continue
        if r > ratio or (r == ratio and best is not None and o_i < best):
            best, ratio = o_i, r
    return best, ratio
