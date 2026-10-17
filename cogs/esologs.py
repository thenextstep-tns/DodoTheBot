"""
ESO Logs Rotation Coaching & Boss Breakdown Cog.
Fetches reports from logs.dodobot.nextstep.team and provides an interactive
Discord UI: Player selection dropdown followed by interactive buttons for
the Overall Summary and each individual Boss fight with in-message pagination.
"""

import asyncio
import re
import urllib.parse
from typing import Dict, List, Optional

import aiohttp
import discord
from discord import app_commands
from discord.ext import commands
from discord.ext.commands import Context

API_BASE_URL = "https://logs.dodobot.nextstep.team"

# Supported classes in the Prophet rotation analyzer
SUPPORTED_CLASSES = {"sorcerer", "arcanist", "necromancer", "dragonknight"}


def extract_and_validate_report_id(raw_url: str) -> Optional[str]:
    """
    Validates that the provided URL is strictly an official esologs.com link
    without redirects, domain spoofing, or tracking parameters, and extracts
    the clean 16-character report ID.
    """
    if not raw_url or not isinstance(raw_url, str):
        return None

    cleaned = raw_url.strip().strip("<>").strip('"').strip("'")
    if not cleaned.startswith(("http://", "https://")):
        cleaned = "https://" + cleaned

    try:
        parsed = urllib.parse.urlparse(cleaned)
    except Exception:
        return None

    # Strict domain verification: must be esologs.com or www.esologs.com
    domain = parsed.hostname.lower() if parsed.hostname else ""
    if domain not in ("esologs.com", "www.esologs.com"):
        return None

    # ESO Logs report IDs are strictly 16 alphanumeric characters
    match = re.search(r"^/reports/([a-zA-Z0-9]{16})(?:[/?#]|$)", parsed.path)
    if not match:
        return None

    return match.group(1)


def paginate_text(text: str, max_chars: int = 1900) -> List[str]:
    """
    Splits text into chunks of at most max_chars, splitting on paragraph
    boundaries (\n\n), then line boundaries (\n), then words, so that
    no markdown formatting or words are awkwardly chopped in half.
    """
    text = text.strip()
    if not text:
        return ["*No content available.*"]
    if len(text) <= max_chars:
        return [text]

    pages: List[str] = []
    lines = text.split("\n")
    current_page_lines: List[str] = []
    current_length = 0

    for line in lines:
        line_len = len(line) + 1
        if current_length + line_len > max_chars and current_page_lines:
            page_str = "\n".join(current_page_lines).strip()
            if page_str:
                pages.append(page_str)
            current_page_lines = []
            current_length = 0

        if len(line) > max_chars:
            words = line.split(" ")
            current_word_line: List[str] = []
            cur_word_len = 0
            for w in words:
                if cur_word_len + len(w) + 1 > max_chars and current_word_line:
                    pages.append(" ".join(current_word_line).strip())
                    current_word_line = []
                    cur_word_len = 0
                current_word_line.append(w)
                cur_word_len += len(w) + 1
            if current_word_line:
                current_page_lines.append(" ".join(current_word_line))
                current_length += cur_word_len
        else:
            current_page_lines.append(line)
            current_length += line_len

    if current_page_lines:
        page_str = "\n".join(current_page_lines).strip()
        if page_str:
            pages.append(page_str)

    return pages if pages else [text[:max_chars]]


def parse_report_sections(full_text: str) -> Dict[str, str]:
    """
    Parses the API markdown report into individual sections:
    - 'summary': Header, Scope, and Key Skill Mechanics overview
    - Boss names (e.g. 'Zilyesset / Count Ryelaz'): Individual boss pull rundown
    """
    sections: Dict[str, str] = {}
    if "### Boss Breakdown" in full_text:
        summary_part, breakdown_part = full_text.split("### Boss Breakdown", 1)
    elif "\n## " in full_text:
        parts = full_text.split("\n## ", 1)
        summary_part = parts[0]
        breakdown_part = "## " + parts[1]
    else:
        summary_part = full_text
        breakdown_part = ""

    sections["summary"] = summary_part.strip()

    # Split pull breakdowns by the '## ' boss headers
    boss_chunks = re.split(r"\n(?=## )", breakdown_part.strip())
    for chunk in boss_chunks:
        chunk = chunk.strip()
        if not chunk.startswith("## "):
            continue
        first_line = chunk.split("\n", 1)[0].replace("## ", "").strip()
        sections[first_line] = chunk

    return sections


class BossFeedbackView(discord.ui.View):
    """
    Interactive View displaying buttons for the Overall Summary, pagination controls,
    and each individual Boss fight.
    All content updates happen in-place within the same message (no spam or multiple messages).
    """

    def __init__(
        self,
        report_id: str,
        actor_name: str,
        spec_name: str,
        summary_text: str,
        boss_breakdowns: Dict[str, str],
        boss_list: List[dict],
        author_id: int,
    ):
        super().__init__(timeout=300)
        self.report_id = report_id
        self.actor_name = actor_name
        self.spec_name = spec_name
        self.summary_text = summary_text.strip()
        self.boss_breakdowns = boss_breakdowns
        self.boss_list = boss_list
        self.author_id = author_id
        self.active_key = "summary"
        self.current_page = 0
        self.current_pages: List[str] = []
        self.message: Optional[discord.Message] = None

        self._update_pages_for_active_key(prefer_boss_page=False)
        self._build_buttons()

    def _update_pages_for_active_key(self, prefer_boss_page: bool = False):
        """Prepares paginated content for the currently active tab."""
        if self.active_key == "summary":
            full_text = self.summary_text
            self.current_pages = paginate_text(full_text, max_chars=1900)
            self.current_page = min(
                self.current_page, max(0, len(self.current_pages) - 1)
            )
        else:
            # Boss breakdown selected: Append boss block below the summary
            boss_text = self.boss_breakdowns.get(self.active_key)
            if not boss_text:
                for b_name, b_val in self.boss_breakdowns.items():
                    if (
                        self.active_key.lower() in b_name.lower()
                        or b_name.lower() in self.active_key.lower()
                    ):
                        boss_text = b_val
                        break
            if not boss_text:
                boss_text = f"No breakdown found for **{self.active_key}**."

            separator = "\n\n" + "═" * 36 + "\n\n"
            full_text = f"{self.summary_text}{separator}{boss_text}"
            self.current_pages = paginate_text(full_text, max_chars=1900)

            if prefer_boss_page:
                target_page = 0
                for p_idx, page in enumerate(self.current_pages):
                    if "═" * 10 in page or self.active_key.lower() in page.lower():
                        target_page = p_idx
                        break
                self.current_page = target_page
            else:
                self.current_page = min(
                    self.current_page, max(0, len(self.current_pages) - 1)
                )

    def _get_current_content(self) -> str:
        """Retrieves page content safely within Discord's 2,000 character limit."""
        if not self.current_pages:
            return "*No content available.*"

        content = self.current_pages[self.current_page]
        total_pages = len(self.current_pages)
        if total_pages > 1:
            page_tag = f"\n\n*(Page {self.current_page + 1}/{total_pages} — use buttons below to navigate)*"
            if len(content) + len(page_tag) <= 2000:
                content += page_tag
        return content

    def _build_buttons(self):
        self.clear_items()
        total_pages = max(1, len(self.current_pages))

        # 1. Row 0: Summary & Pagination Controls
        summary_btn = discord.ui.Button(
            label="Summary",
            style=(
                discord.ButtonStyle.primary
                if self.active_key == "summary"
                else discord.ButtonStyle.secondary
            ),
            emoji="📋",
            row=0,
        )
        summary_btn.callback = self._on_summary_click
        self.add_item(summary_btn)

        prev_btn = discord.ui.Button(
            label="Prev",
            style=discord.ButtonStyle.secondary,
            emoji="◀",
            disabled=(self.current_page <= 0),
            row=0,
        )
        prev_btn.callback = self._on_prev_click
        self.add_item(prev_btn)

        page_btn = discord.ui.Button(
            label=f"{self.current_page + 1}/{total_pages}",
            style=discord.ButtonStyle.secondary,
            disabled=True,
            row=0,
        )
        self.add_item(page_btn)

        next_btn = discord.ui.Button(
            label="Next",
            style=discord.ButtonStyle.secondary,
            emoji="▶",
            disabled=(self.current_page >= total_pages - 1),
            row=0,
        )
        next_btn.callback = self._on_next_click
        self.add_item(next_btn)

        # 2. Rows 1-4: Boss Buttons (Up to 20 bosses)
        for idx, boss in enumerate(self.boss_list[:20], start=1):
            boss_name = boss.get("name", f"Boss {idx}")
            row_num = min(4, 1 + ((idx - 1) // 5))
            label = f"{idx}. {boss_name}"
            if len(label) > 80:
                label = label[:77] + "..."

            is_active = self.active_key == boss_name
            btn = discord.ui.Button(
                label=label,
                style=(
                    discord.ButtonStyle.primary
                    if is_active
                    else discord.ButtonStyle.secondary
                ),
                emoji="💀" if boss.get("kill") else "⚔️",
                row=row_num,
            )

            def make_boss_callback(b_name: str):
                async def boss_callback(interaction: discord.Interaction):
                    if interaction.user.id != self.author_id:
                        await interaction.response.send_message(
                            "This interaction is for the command author.",
                            ephemeral=True,
                        )
                        return
                    self.active_key = b_name
                    self._update_pages_for_active_key(prefer_boss_page=True)
                    self._build_buttons()
                    await interaction.response.edit_message(
                        content=self._get_current_content(), view=self
                    )

                return boss_callback

            btn.callback = make_boss_callback(boss_name)
            self.add_item(btn)

    async def _on_summary_click(self, interaction: discord.Interaction):
        if interaction.user.id != self.author_id:
            await interaction.response.send_message(
                "This interaction is for the command author.", ephemeral=True
            )
            return
        self.active_key = "summary"
        self.current_page = 0
        self._update_pages_for_active_key(prefer_boss_page=False)
        self._build_buttons()
        await interaction.response.edit_message(
            content=self._get_current_content(), view=self
        )

    async def _on_prev_click(self, interaction: discord.Interaction):
        if interaction.user.id != self.author_id:
            await interaction.response.send_message(
                "This interaction is for the command author.", ephemeral=True
            )
            return
        if self.current_page > 0:
            self.current_page -= 1
            self._build_buttons()
            await interaction.response.edit_message(
                content=self._get_current_content(), view=self
            )

    async def _on_next_click(self, interaction: discord.Interaction):
        if interaction.user.id != self.author_id:
            await interaction.response.send_message(
                "This interaction is for the command author.", ephemeral=True
            )
            return
        if self.current_page < len(self.current_pages) - 1:
            self.current_page += 1
            self._build_buttons()
            await interaction.response.edit_message(
                content=self._get_current_content(), view=self
            )

    async def on_timeout(self):
        for child in self.children:
            if isinstance(child, discord.ui.Button):
                child.disabled = True
        try:
            if self.message:
                await self.message.edit(view=self)
        except Exception:
            pass


class PlayerSelect(discord.ui.Select):
    """Dropdown for choosing a player from the log with spec support indicators."""

    def __init__(
        self,
        report_id: str,
        friendlies: List[dict],
        author_id: int,
    ):
        self.report_id = report_id
        self.author_id = author_id

        options = []
        valid_players = [
            f
            for f in friendlies
            if f.get("type") not in ("NPC", "Pet", "Boss", "Unknown")
        ]

        for p in valid_players[:25]:
            p_name = p.get("name", "Unknown")
            p_class = p.get("type", "Unknown")
            p_id = p.get("id")
            display_name = p.get("displayName")

            is_supported = p_class.lower() in SUPPORTED_CLASSES

            if is_supported:
                desc = (
                    f"{p_class} ({display_name})"
                    if display_name
                    else f"{p_class}"
                )
                emoji = "⚔️"
                val = f"supported_{p_id}_{p_name}"
            else:
                desc = f"{p_class} — CAN'T ANALYSE YET"
                emoji = "⚠️"
                val = f"unsupported_{p_id}_{p_name}_{p_class}"

            options.append(
                discord.SelectOption(
                    label=p_name[:100],
                    description=desc[:100],
                    value=val,
                    emoji=emoji,
                )
            )

        super().__init__(
            placeholder="Select a player from this report...",
            min_values=1,
            max_values=1,
            options=options,
        )

    async def callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.author_id:
            await interaction.response.send_message(
                "This interaction is for the command author.", ephemeral=True
            )
            return

        selected_val = self.values[0]

        if selected_val.startswith("unsupported_"):
            parts = selected_val.split("_", 3)
            p_name = parts[2] if len(parts) > 2 else "This player"
            p_class = parts[3] if len(parts) > 3 else "this class"
            await interaction.response.send_message(
                f"⚠️ **Cannot Analyze Yet**: **{p_name}** is playing **{p_class}**.\n"
                f"Rotation coaching is currently available for: **Sorcerer**, **Arcanist**, **Necromancer**, and **Dragonknight**.\n"
                f"Please select a player with a supported spec from the dropdown.",
                ephemeral=True,
            )
            return

        parts = selected_val.split("_", 2)
        player_id = parts[1]
        player_name = parts[2] if len(parts) > 2 else player_id

        await interaction.response.defer()

        feedback_url = f"{API_BASE_URL}/api/boss-feedback"
        params = {
            "reportId": self.report_id,
            "player": str(player_id),
            "format": "json",
            "killsOnly": "true",
            "includeKeySkills": "true",
        }

        async with aiohttp.ClientSession() as session:
            try:
                async with session.get(
                    feedback_url,
                    params=params,
                    timeout=aiohttp.ClientTimeout(total=45),
                ) as resp:
                    if resp.status != 200:
                        err_data = await resp.json()
                        err_msg = err_data.get(
                            "error", f"HTTP {resp.status} error from service."
                        )
                        await interaction.followup.send(
                            f"❌ Error analyzing {player_name}: {err_msg}",
                            ephemeral=True,
                        )
                        return
                    data = await resp.json()
            except Exception as e:
                await interaction.followup.send(
                    f"⚠️ Failed to reach rotation service at `{API_BASE_URL}`: {e}",
                    ephemeral=True,
                )
                return

        report_text = data.get("reportText", "")
        boss_list = data.get("bossFightsList", [])
        spec_name = data.get("specName", "DPS")
        overall_summary = data.get("overallSummary")

        sections = parse_report_sections(report_text)
        if not overall_summary:
            overall_summary = sections.get("summary", report_text)

        boss_breakdowns: Dict[str, str] = {}
        for b in boss_list:
            b_name = b.get("name", "")
            if b.get("breakdownText"):
                boss_breakdowns[b_name] = b.get("breakdownText")
            elif b_name in sections:
                boss_breakdowns[b_name] = sections[b_name]

        for sec_name, sec_text in sections.items():
            if sec_name != "summary" and sec_name not in boss_breakdowns:
                boss_breakdowns[sec_name] = sec_text

        # Build button view for Summary + each boss fight with in-message pagination
        view = BossFeedbackView(
            report_id=self.report_id,
            actor_name=player_name,
            spec_name=spec_name,
            summary_text=overall_summary,
            boss_breakdowns=boss_breakdowns,
            boss_list=boss_list,
            author_id=self.author_id,
        )

        initial_content = view._get_current_content()
        msg = await interaction.followup.send(content=initial_content, view=view)
        view.message = msg


class PlayerSelectView(discord.ui.View):
    """View holding the player selection dropdown."""

    def __init__(
        self, report_id: str, friendlies: List[dict], author_id: int
    ):
        super().__init__(timeout=180)
        self.add_item(PlayerSelect(report_id, friendlies, author_id))


class EsoLogs(commands.Cog, name="esologs"):
    """ESO Logs rotation feedback and analysis."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.hybrid_command(
        name="esologs",
        description="Analyze rotation performance and boss feedback from an ESO Logs report.",
    )
    @app_commands.describe(
        link="Official ESO Logs report link (e.g. https://www.esologs.com/reports/...)"
    )
    async def esologs(
        self, context: Context, link: Optional[str] = None
    ) -> None:
        """Analyze rotation coaching and boss breakdowns from an ESO Logs report."""

        # Immediately acknowledge to satisfy Discord's 3-second gateway timeout rule
        await context.defer()

        # 1. If link is not provided as an argument, ask the user to provide it
        if not link:
            await context.reply(
                "Please provide the official `esologs.com` report link to analyze:"
            )

            def check_author(m: discord.Message) -> bool:
                return (
                    m.author.id == context.author.id
                    and m.channel.id == context.channel.id
                )

            try:
                user_msg = await self.bot.wait_for(
                    "message", check=check_author, timeout=60.0
                )
                link = user_msg.content
            except asyncio.TimeoutError:
                await context.reply(
                    "⏱️ No link provided in time. Please run `/esologs` again when ready."
                )
                return

        # 2. Strict URL validation: strictly esologs.com links, strip to 16-char report ID
        report_id = extract_and_validate_report_id(link)
        if not report_id:
            await context.reply(
                "❌ **Invalid ESO Logs Link**\n"
                "Please provide a valid link to an official report on `https://www.esologs.com/reports/<report_id>`.\n"
                "*(Example: `https://www.esologs.com/reports/zHCFNYL8Whcqfypn`)*"
            )
            return

        # 3. Fetch report details from API to retrieve the friendly roster
        status_msg = await context.reply(
            f"🔍 Fetching roster for report `{report_id}`..."
        )

        rotation_url = f"{API_BASE_URL}/api/rotation"
        params = {"reportId": report_id}

        async with aiohttp.ClientSession() as session:
            try:
                async with session.get(
                    rotation_url,
                    params=params,
                    timeout=aiohttp.ClientTimeout(total=30),
                ) as resp:
                    if resp.status != 200:
                        err_data = await resp.json()
                        err_msg = err_data.get(
                            "error", f"HTTP {resp.status} error from service."
                        )
                        await status_msg.edit(
                            content=f"❌ Could not load report `{report_id}`: {err_msg}"
                        )
                        return
                    data = await resp.json()
            except Exception as e:
                await status_msg.edit(
                    content=f"⚠️ Failed to reach rotation service at `{API_BASE_URL}`: {e}"
                )
                return

        friendlies = data.get("friendlies", [])
        report_title = data.get("reportTitle", report_id)

        if not friendlies:
            await status_msg.edit(
                content=f"❌ No player characters found in report `{report_id}`."
            )
            return

        # 4. Ask: "Who do you need feedback on?" with dropdown of known specs
        select_view = PlayerSelectView(report_id, friendlies, context.author.id)
        prompt_text = (
            f"📊 **Report**: *{report_title}* (`{report_id}`)\n"
            f"**Who do you need feedback on?**"
        )
        await status_msg.edit(content=prompt_text, view=select_view)


async def setup(bot: commands.Bot):
    await bot.add_cog(EsoLogs(bot))
