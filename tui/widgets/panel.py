"""
OverCR TUI — Panel Widget v2.2.0

Bordered panel rendering using rich.panel.Panel.
Wraps content in a titled, bordered container.
Deterministic: same content always renders same output.
"""

from rich.console import Console
from rich.panel import Panel
from rich.text import Text
from typing import Optional

from tui.theme import Theme


class PanelWidget:
    """
    A bordered panel for grouping content.

    Renders content inside a titled, bordered container.
    Deterministic: same inputs always produce same output.
    """

    def __init__(
        self,
        title: str = "",
        console: Optional[Console] = None,
    ):
        self.title = title
        self.console = console or Console()

    def render(
        self,
        content: str,
        subtitle: str = "",
        style: str = "",
        border_style: str = "",
    ) -> str:
        """
        Render content inside a bordered panel.

        Args:
            content: The text content to wrap.
            subtitle: Optional subtitle for the panel.
            style: Rich style for the panel content.
            border_style: Rich style for the panel border.

        Returns:
            Rich-formatted string.
        """
        panel = Panel(
            Text.from_markup(content) if "[" in content else content,
            title=self.title,
            subtitle=subtitle or None,
            border_style=border_style or Theme.PANEL_BORDER_STYLE,
            style=style or None,
            padding=(0, Theme.PANEL_PADDING),
        )

        with self.console.capture() as capture:
            self.console.print(panel)
        return capture.get()

    def render_plain(self, content: str, width: int = 72) -> str:
        """
        Render a plain-text fallback panel (no rich markup).

        Uses box-drawing characters or ASCII fallback.
        """
        lines = content.split("\n")
        inner_width = width - 4  # borders and padding

        # Wrap lines that are too long
        wrapped = []
        for line in lines:
            while len(line) > inner_width:
                wrapped.append(line[:inner_width])
                line = line[inner_width:]
            wrapped.append(line)

        result = []
        border_top = "+" + "-" * (inner_width + 2) + "+"
        border_bot = border_top

        result.append(border_top)

        if self.title:
            title_line = f"| {self.title:^{inner_width}} |"
            result.append(title_line)
            result.append(border_top)

        for line in wrapped:
            result.append(f"| {line:<{inner_width}} |")

        result.append(border_bot)
        return "\n".join(result)