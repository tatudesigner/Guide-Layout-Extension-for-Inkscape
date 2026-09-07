# Copyright (C) 2024 Tatudesigner <heriton.agoncalves@gmail.com>
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software Foundation,
# Inc., 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301 USA.
#
# ---------------------------------------------------------------------------
# Guide Layout
#
# Lightweight version, in the spirit of Photoshop's "New Guide Layout"
# dialog: creates ONLY real Inkscape guides (the same lines you drag
# from the ruler) — no rectangle, drawn line, or SVG object is created.
# Columns and Rows are independent checkboxes (checking both = modular
# grid), simple margins (Top/Bottom/Left/Right), customizable guide
# color, and an option to clear existing guides.
# ---------------------------------------------------------------------------

import inkex
from inkex.localization import inkex_gettext as _

# Unit conversions
CONVERSIONS = {
    'in': 96.0,
    'pt': 1.3333333333333333,
    'px': 1.0,
    'mm': 3.779527559055118,
    'cm': 37.79527559055118,
    'm': 3779.527559055118,
    'km': 3779527.559055118,
    'Q': 0.94488188976378,
    'pc': 16.0,
    'yd': 3456.0,
    'ft': 1152.0,
    '': 1.0,  # Default px
}


class GuideLayout(inkex.EffectExtension):

    # -------------------------------------------------------------------
    # ARGUMENTS
    # -------------------------------------------------------------------

    def add_arguments(self, pars):
        # Columns
        pars.add_argument("--enable_columns", type=inkex.Boolean, default=True)
        pars.add_argument("--columns_count", type=int, default=12)
        pars.add_argument("--column_width", type=float, default=0,
                           help="0 = automatic (fills the usable area)")
        pars.add_argument("--gutter_h", type=float, default=16)

        # Rows
        pars.add_argument("--enable_rows", type=inkex.Boolean, default=False)
        pars.add_argument("--rows_count", type=int, default=6)
        pars.add_argument("--row_height", type=float, default=0,
                           help="0 = automatic (fills the usable area)")
        pars.add_argument("--gutter_v", type=float, default=16)

        # Simple margins (Top/Bottom/Left/Right)
        pars.add_argument("--enable_margins", type=inkex.Boolean, default=False)
        pars.add_argument("--margin_top", type=float, default=0)
        pars.add_argument("--margin_bottom", type=float, default=0)
        pars.add_argument("--margin_left", type=float, default=0)
        pars.add_argument("--margin_right", type=float, default=0)

        # Guide color
        pars.add_argument("--guide_color", type=inkex.Color, default=inkex.Color("#0066ffff"))

        # Cleanup
        pars.add_argument("--clear_existing", type=inkex.Boolean, default=False)

    # -------------------------------------------------------------------
    # EFFECT
    # -------------------------------------------------------------------

    def effect(self):
        if self.options.clear_existing:
            self.clear_existing_guides()

        page_width, page_height = self.get_page_dimensions()
        # Prevents creating two guides at the same position (e.g. when
        # the grid in automatic mode already touches the margin exactly).
        self._guide_positions = set()

        enable_columns = self.options.enable_columns
        enable_rows = self.options.enable_rows
        enable_margins = self.options.enable_margins

        if not (enable_columns or enable_rows or enable_margins):
            inkex.errormsg(_("Select at least one option: Columns, Rows, or Margin."))
            return

        # Margins only factor into the calculation (and only generate
        # guides) if the "Margin" checkbox is checked — otherwise the
        # usable area is the whole page, matching Photoshop's behavior.
        if enable_margins:
            margins = {
                'top': self.to_px(self.options.margin_top),
                'bottom': self.to_px(self.options.margin_bottom),
                'left': self.to_px(self.options.margin_left),
                'right': self.to_px(self.options.margin_right),
            }
            error = self.validate_margins(margins, page_width, page_height)
            if error:
                inkex.errormsg(error)
                return
        else:
            margins = {'top': 0, 'bottom': 0, 'left': 0, 'right': 0}

        origin_x = margins['left']
        origin_y = margins['top']
        usable_width = page_width - margins['left'] - margins['right']
        usable_height = page_height - margins['top'] - margins['bottom']

        # Columns/Rows validation: basic parameters (count, gutter) and,
        # when Width/Height is fixed, whether the grid fits the usable
        # area — since in that case it doesn't automatically adjust to
        # the available space.
        error = self.validate_grid_parameters(enable_columns, enable_rows, usable_width, usable_height)
        if error:
            inkex.errormsg(error)
            return

        if enable_columns and enable_rows:
            self.create_modular_guides(origin_x, origin_y, usable_width, usable_height)
        elif enable_columns:
            self.create_columns_guides(origin_x, origin_y, usable_width)
        elif enable_rows:
            self.create_rows_guides(origin_x, origin_y, usable_height)

        # Margin guides: always all 4 (top, bottom, left, right) when
        # "Margin" is checked — independent of Columns/Rows. When
        # Columns/Rows are also active, these guides coincide with the
        # grid's outer edges and effectively function as margins (same
        # behavior as Photoshop's "New Guide Layout").
        if enable_margins:
            self.add_margin_guides(origin_x, origin_y, usable_width, usable_height)

    # -------------------------------------------------------------------
    # CLEANUP (in the style of Photoshop's "Clear Existing Guides")
    # -------------------------------------------------------------------

    def clear_existing_guides(self):
        """Removes all existing guides (and 'Grid N' layers from earlier
        versions of the script that used to draw rectangles, if any)."""
        existing_grids = self.svg.xpath('//svg:g[starts-with(@inkscape:label, "Grid ")]', namespaces=inkex.NSS)
        for grid in existing_grids:
            parent = grid.getparent()
            if parent is not None:
                parent.remove(grid)

        namedview = self.svg.namedview
        existing_guides = namedview.xpath('sodipodi:guide', namespaces=inkex.NSS)
        for guide in existing_guides:
            namedview.remove(guide)

    # -------------------------------------------------------------------
    # DIMENSIONS / MARGINS
    # -------------------------------------------------------------------

    def get_page_dimensions(self):
        pixel_conversion_factor = CONVERSIONS[self.svg.unit]
        return (
            self.svg.viewbox_width * pixel_conversion_factor,
            self.svg.viewbox_height * pixel_conversion_factor
        )

    def to_px(self, value):
        """Converts a value entered by the user (in the document's unit
        — cm, mm, px, etc., whatever is set in File > Document
        Properties) to px, the internal unit used in the calculations."""
        return value * CONVERSIONS[self.svg.unit]

    def validate_margins(self, margins, page_width, page_height):
        """Returns an error message if the margins are invalid, or None
        if they're OK."""
        if any(v < 0 for v in margins.values()):
            return _("Margins cannot be negative.")
        if margins['left'] + margins['right'] >= page_width:
            return _("Left and right margins combined exceed the page width.")
        if margins['top'] + margins['bottom'] >= page_height:
            return _("Top and bottom margins combined exceed the page height.")
        return None

    def validate_grid_parameters(self, enable_columns, enable_rows, usable_width, usable_height):
        """Returns an error message if the Columns/Rows parameters are
        invalid, or if a fixed Width/Height doesn't fit the usable area
        (since in that case the grid doesn't automatically adjust to the
        available space). Returns None if everything is fine."""
        o = self.options

        if enable_columns and (o.columns_count <= 0 or o.gutter_h < 0 or o.column_width < 0):
            return _("Invalid Columns parameters. Check Number, Width, and Gutter.")
        if enable_rows and (o.rows_count <= 0 or o.gutter_v < 0 or o.row_height < 0):
            return _("Invalid Rows parameters. Check Number, Height, and Gutter.")

        if enable_columns and o.column_width > 0:
            gutter = self.to_px(o.gutter_h)
            width = self.to_px(o.column_width)
            total_width = o.columns_count * width + gutter * (o.columns_count - 1)
            if total_width > usable_width:
                return _(
                    "The space taken up by Columns (Width, Number, and Gutter) is larger than the "
                    "available usable area. Reduce these values or decrease the margins."
                )
        if enable_rows and o.row_height > 0:
            gutter = self.to_px(o.gutter_v)
            height = self.to_px(o.row_height)
            total_height = o.rows_count * height + gutter * (o.rows_count - 1)
            if total_height > usable_height:
                return _(
                    "The space taken up by Rows (Height, Number, and Gutter) is larger than the "
                    "available usable area. Reduce these values or decrease the margins."
                )
        return None

    def _resolve_size(self, fixed_value, count, gutter, usable_size):
        """Calculates the size (column width or row height) in px. If
        fixed_value <= 0 (automatic), the size fills usable_size divided
        by count, minus the gutters. Otherwise, converts fixed_value to
        px and uses it as-is."""
        if fixed_value <= 0:
            return (usable_size - gutter * (count - 1)) / count
        return self.to_px(fixed_value)

    # -------------------------------------------------------------------
    # COLUMNS (guides only)
    # -------------------------------------------------------------------

    def create_columns_guides(self, origin_x, origin_y, usable_width):
        count = self.options.columns_count
        gutter = self.to_px(self.options.gutter_h)
        width = self._resolve_size(self.options.column_width, count, gutter, usable_width)

        # Anchors to the left (origin_x) — see _resolve_size() for the
        # auto vs. fixed logic.
        x = origin_x

        for __ in range(count):
            self.add_guide(x, origin_y, orientation="vertical")
            self.add_guide(x + width, origin_y, orientation="vertical")
            x += width + gutter

    # -------------------------------------------------------------------
    # ROWS (guides only)
    # -------------------------------------------------------------------

    def create_rows_guides(self, origin_x, origin_y, usable_height):
        count = self.options.rows_count
        gutter = self.to_px(self.options.gutter_v)
        height = self._resolve_size(self.options.row_height, count, gutter, usable_height)

        # Anchors to the top (origin_y) — see _resolve_size() for the
        # auto vs. fixed logic.
        y = origin_y

        for __ in range(count):
            self.add_guide(origin_x, y, orientation="horizontal")
            self.add_guide(origin_x, y + height, orientation="horizontal")
            y += height + gutter

    # -------------------------------------------------------------------
    # MODULAR (Columns + Rows at the same time, guides only)
    # -------------------------------------------------------------------

    def create_modular_guides(self, origin_x, origin_y, usable_width, usable_height):
        cols = self.options.columns_count
        rows = self.options.rows_count
        gutter_h = self.to_px(self.options.gutter_h)
        gutter_v = self.to_px(self.options.gutter_v)

        col_width = self._resolve_size(self.options.column_width, cols, gutter_h, usable_width)
        row_height = self._resolve_size(self.options.row_height, rows, gutter_v, usable_height)

        # Anchors to the left/top — see _resolve_size() for the auto vs.
        # fixed logic (same one used in create_columns_guides/rows_guides).
        grid_x0 = origin_x
        grid_y0 = origin_y

        gx = grid_x0
        for __ in range(cols):
            self.add_guide(gx, grid_y0, orientation="vertical")
            self.add_guide(gx + col_width, grid_y0, orientation="vertical")
            gx += col_width + gutter_h

        gy = grid_y0
        for __ in range(rows):
            self.add_guide(grid_x0, gy, orientation="horizontal")
            self.add_guide(grid_x0, gy + row_height, orientation="horizontal")
            gy += row_height + gutter_v

    # -------------------------------------------------------------------
    # MARGIN GUIDES (always created, delimit the usable area)
    # -------------------------------------------------------------------

    def add_margin_guides(self, origin_x, origin_y, usable_width, usable_height):
        self.add_guide(origin_x, origin_y, orientation="vertical")
        self.add_guide(origin_x + usable_width, origin_y, orientation="vertical")
        self.add_guide(origin_x, origin_y, orientation="horizontal")
        self.add_guide(origin_x, origin_y + usable_height, orientation="horizontal")

    # -------------------------------------------------------------------
    # GUIDE (sodipodi:guide element — a real Inkscape ruler guide)
    # -------------------------------------------------------------------

    def add_guide(self, x_px, y_px, orientation="vertical"):
        """
        Creates a real Inkscape guide (sodipodi:guide) — the same line
        you'd drag manually from the ruler.

        Uses the official inkex API (self.svg.namedview.add_guide), the
        same one used by the "Guides Creator" extension bundled with
        Inkscape. This API expects the Y coordinate in the normal
        direction (top to bottom, same as the rest of this script) and
        converts it internally to the file format (which measures from
        the bottom of the page) — so we do NOT flip Y here; flipping it
        again would cause a double flip.

        Guides at the same position (same coordinate relevant to the
        same orientation) are not duplicated — this happens, for
        example, when the grid in automatic mode already touches the
        margin exactly.
        """
        dedup_value = x_px if orientation == "vertical" else y_px
        dedup_key = (orientation, round(dedup_value, 4))
        if dedup_key in self._guide_positions:
            return
        self._guide_positions.add(dedup_key)

        unit_factor = CONVERSIONS[self.svg.unit]
        x = x_px / unit_factor
        y = y_px / unit_factor

        direction = [1, 0] if orientation == "vertical" else [0, -1]

        guide = self.svg.namedview.add_guide([x, y], direction)
        if guide is not None:
            guide.set('inkscape:color', self.options.guide_color.to_rgb())


if __name__ == '__main__':
    GuideLayout().run()
