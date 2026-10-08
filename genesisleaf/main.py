"""Program entry point.

Part of GenesisLeaf 0x01a - see docs/ARCHITECTURE.md.
"""

import argparse
import tkinter as tk

def _enable_diagnostics(root, debug, app_class):
    from genesisleaf.diagnostics import install, trace_methods, traced
    from genesisleaf.core import pairing, space
    from genesisleaf.core.pack import Pack
    from genesisleaf.ui import canvas_render
    from genesisleaf.ui.windows.view import ViewWindow

    monitor = install(root, verbose=True, debug=debug)
    trace_methods(app_class, (
        "__init__", "load_pack", "_load_pack_async", "_load_poll",
        "_after_pack_loaded", "save_pack", "save_pack_as",
        "rebuild_view", "_insert_plan", "sort_by", "select_entry",
        "on_tree_select", "jump_to_flat", "_on_rowkey", "_alt_nav",
        "_see_if_needed", "_set_tree_selection", "_select_box",
        "_load_meta", "_selected_flat_in_order", "_sync_tr_editors",
        "_ed_rows_for", "_load_ed_rows", "retag",
        "_tr_modified_common", "on_tr_modified",
        "update_preview", "_draw_dyn_preview", "_draw_float_preview",
        "_on_dyn_resize", "_run_dyn_resize", "_cmp_start", "_cmp_poll",
        "_cmp_apply_filter", "_insert_cmp_rows", "_cmp_show_detail",
        "_cmp_preview_rows", "_cmp_draw_location", "_cmp_run_resize",
        "_cmp_on_select", "_cmp_on_yscroll", "_cmp_draw_viewport",
        "_cmp_follow_main", "_cmp_follow_now", "_cmp_see_if_needed",
        "_cmp_detail_now",
        "_cmp_update_pos_label", "_cmp_fill_diff_pane", "_cmp_find_diffs",
        "update_cmp_summary", "refresh_compare",
        "update_status", "_stats_recompute", "_stats_poll",
        "invalidate_stats", "_refresh_navigator", "_join_groups",
        "_run_scheduled_join", "_update_clone_label", "_update_words",
        "_bytes_label", "_refresh_ctx_filter", "_update_space_lab",
        "_run_scheduled_search", "apply_theme", "on_close",
    ))
    trace_methods(ViewWindow, ("rebuild_view", "_insert_rows", "_load_editor",
                               "on_tr_modified", "close"))
    trace_methods(Pack, ("load", "stats", "rebuild_indexes", "dialog_box_map"))
    trace_methods(canvas_render.CanvasRenderQueue, ("request", "_poll"))
    pairing.match = traced("pairing.match")(pairing.match)
    pairing.snapshot = traced("pairing.snapshot")(pairing.snapshot)
    space.estimate = traced("space.estimate")(space.estimate)
    canvas_render.render_font_rows = traced("render_font_rows")(
        canvas_render.render_font_rows)
    canvas_render.render_text_to_canvas = traced("render_text_to_canvas")(
        canvas_render.render_text_to_canvas)
    return monitor


def main(argv=None):
    parser = argparse.ArgumentParser(description="GenesisLeaf translation editor")
    parser.add_argument("pack", nargs="?", help="YAML pack to open")
    parser.add_argument("--verbose", action="store_true",
                        help="print timestamped operations, stages, input and UI lag")
    parser.add_argument("--debug", action="store_true",
                        help="print verbose diagnostics and write a timestamped .log")
    args = parser.parse_args(argv)
    from genesisleaf.ui.app.app import App
    from genesisleaf.ui.fonts import (
        FONT_DEFAULT_FAMILY, FONT_MONO, FONT_UI_SM, init_fonts,
    )
    root = tk.Tk()
    root.withdraw()             # present the finished window, not widget-by-widget assembly
    monitor = _enable_diagnostics(root, args.debug, App) \
        if (args.verbose or args.debug) else None
    init_fonts(root, FONT_DEFAULT_FAMILY)
    # Default font for every widget that does not set one explicitly (labels,
    # buttons, tabs, treeview cells, dialogs) so the whole editor is monospace.
    root.option_add("*font", FONT_MONO)
    root.option_add("*TCombobox*Listbox.font", FONT_UI_SM)
    app = App(root, pack_path=args.pack)
    if monitor is not None:
        monitor.attach(app.diagnostic_label)
        print("[GenesisLeaf] diagnostics: %s" %
              (monitor.log_path or "console only"), flush=True)
    root.update_idletasks()
    try:
        root.attributes("-alpha", 0.0)
        transparent_start = True
    except tk.TclError:
        transparent_start = False
    root.deiconify()
    if transparent_start:
        # Windows lays out several panes only after the toplevel is mapped.
        # Let those idle geometry passes finish while the window is invisible.
        root.update_idletasks()
        app._initial_sashes()
        root.update_idletasks()
        root.attributes("-alpha", 1.0)
    try:
        root.mainloop()
    finally:
        if monitor is not None:
            monitor.close()
