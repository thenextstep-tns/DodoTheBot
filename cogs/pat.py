"""
PAT decoder cog — reads a screenshot of a trial-clear (PAT) table posted in the
decode channel, OCRs it, fuzzy-matches trial names, and assigns the matching
clear roles to the poster.

Requires the Tesseract OCR binary to be installed on the host at runtime.
"""

import difflib
import io
import re

import aiohttp
import cv2
import numpy as np
import pytesseract
from PIL import Image

import discord
from discord.ext import commands

import config_py
import lang
from helpers import messages

_CHECKBOX_POSITIVE = {"✓", "✔", "✅", "v"}
_OCR_SCALE_PERCENT = 300
_OCR_CONFIG = r"--psm 6"


class PATRoleAssigner(commands.Cog, name="pat"):
    """Assigns trial-clear roles by OCR-decoding a posted PAT screenshot."""

    def __init__(self, bot):
        self.bot = bot
        self.known_trials = sorted(
            set(config_py.vet_clears)
            | set(config_py.hm_partial_clears_1_boss)
            | set(config_py.hm_partial_clears_2_boss)
            | set(config_py.hm_clears)
        )

    @staticmethod
    async def _download(url: str) -> io.BytesIO | None:
        """Download an image URL into an in-memory buffer."""
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as resp:
                if resp.status != 200:
                    return None
                return io.BytesIO(await resp.read())

    @staticmethod
    def _preprocess(image_data: io.BytesIO) -> Image.Image:
        """Grayscale, upscale and threshold the image so OCR reads it better."""
        cv_image = cv2.cvtColor(np.array(Image.open(image_data)), cv2.COLOR_RGB2BGR)
        gray = cv2.cvtColor(cv_image, cv2.COLOR_BGR2GRAY)
        width = int(gray.shape[1] * _OCR_SCALE_PERCENT / 100)
        height = int(gray.shape[0] * _OCR_SCALE_PERCENT / 100)
        gray = cv2.resize(gray, (width, height), interpolation=cv2.INTER_CUBIC)
        _, thresh = cv2.threshold(gray, 180, 255, cv2.THRESH_BINARY)
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (1, 1))
        thresh = cv2.morphologyEx(thresh, cv2.MORPH_OPEN, kernel, iterations=1)
        thresh = cv2.morphologyEx(thresh, cv2.MORPH_CLOSE, kernel, iterations=1)
        return Image.fromarray(thresh)

    def _extract_lines(self, processed_image: Image.Image) -> list[str]:
        """Run Tesseract and return the non-empty OCR lines."""
        text = pytesseract.image_to_string(processed_image, lang="eng", config=_OCR_CONFIG)
        lines = text.splitlines()
        self.bot.logger.debug(f"PAT OCR lines: {lines}")
        return lines

    def _roles_from_lines(self, lines: list[str], guild_roles: dict[int, discord.Role]) -> list[discord.Role]:
        """Parse each OCR line into a matched trial and its highest-cleared role."""
        roles: list[discord.Role] = []
        for raw_line in lines:
            tokens = raw_line.strip().split()
            if len(tokens) < 5:
                continue

            columns = tokens[-4:]  # vet / hm1 / hm2 / hm3 checkboxes
            name_tokens = tokens[:-4]
            # Drop a trailing numeric score token if present.
            while name_tokens and re.match(r"^[\d,.\']+$", name_tokens[-1]):
                name_tokens.pop()

            match = difflib.get_close_matches(" ".join(name_tokens), self.known_trials, n=1, cutoff=0.5)
            if not match:
                continue
            trial = match[0]

            vet, hm1, hm2, hm3 = (symbol in _CHECKBOX_POSITIVE for symbol in columns)
            # Highest clear wins.
            if hm3:
                role_id = config_py.hm_clears.get(trial)
            elif hm2:
                role_id = config_py.hm_partial_clears_2_boss.get(trial)
            elif hm1:
                role_id = config_py.hm_partial_clears_1_boss.get(trial)
            elif vet:
                role_id = config_py.vet_clears.get(trial)
            else:
                role_id = None

            if role_id and (role := guild_roles.get(role_id)):
                roles.append(role)
        return roles

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        if message.channel.id != config_py.PAT_DECODE_CHANNEL or message.author.bot:
            return
        if message.guild and not self.bot.visibility.feature_active(message.guild.id, "pat_decode", "pat"):
            return
        if not message.attachments:
            return

        image_data = await self._download(message.attachments[0].url)
        if image_data is None:
            await message.channel.send(lang.PAT_DOWNLOAD_FAILED)
            return

        lines = self._extract_lines(self._preprocess(image_data))
        guild_roles = {role.id: role for role in message.guild.roles}
        roles = list(dict.fromkeys(self._roles_from_lines(lines, guild_roles)))  # de-dupe, keep order

        if not roles:
            await message.channel.send(lang.PAT_NO_ROLES.format(mention=message.author.mention))
            return

        await message.author.add_roles(*roles)
        embed = messages.success(
            lang.PAT_ASSIGNED_DESCRIPTION.format(mention=message.author.mention), title=lang.PAT_ASSIGNED_TITLE
        )
        embed.add_field(name="Roles", value="\n".join(role.name for role in roles), inline=False)
        await message.channel.send(embed=embed)


async def setup(bot):
    await bot.add_cog(PATRoleAssigner(bot))
