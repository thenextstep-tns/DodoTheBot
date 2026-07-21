import disnake
from disnake.ext import commands
import aiohttp
import io
import cv2
import numpy as np
from PIL import Image
import pytesseract
import re
import config_py

# We'll use Python's built-in "difflib" for fuzzy matching
import difflib

class PATRoleAssignerFuzzy(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

        # Prepare a list of known trial names from your dictionaries
        self.known_trials = set()
        self.known_trials.update(config_py.vet_clears.keys())
        self.known_trials.update(config_py.hm_partial_clears_1_boss.keys())
        self.known_trials.update(config_py.hm_partial_clears_2_boss.keys())
        self.known_trials.update(config_py.hm_clears.keys())
        # Convert to a sorted list so difflib can operate on it
        self.known_trials = sorted(self.known_trials)

        # Symbols considered "checked"
        self.checkbox_positive = ['✓', '✔', '✅', 'v']

    @commands.Cog.listener()
    async def on_message(self, message: disnake.Message):
        # Only proceed if this is in the specific channel and not from a bot
        if message.channel.id != config_py.PAT_DECODE_CHANNEL or message.author.bot:
            return

        if not message.attachments:
            return

        image_url = message.attachments[0].url

        # Download the image
        async with aiohttp.ClientSession() as session:
            async with session.get(image_url) as resp:
                if resp.status != 200:
                    await message.channel.send('Failed to download image.')
                    return
                image_data = io.BytesIO(await resp.read())

        # ============= PREPROCESSING WITH OPENCV =============
        pil_image = Image.open(image_data)
        cv_image = cv2.cvtColor(np.array(pil_image), cv2.COLOR_RGB2BGR)

        # 1) Convert to grayscale
        gray = cv2.cvtColor(cv_image, cv2.COLOR_BGR2GRAY)

        # 2) Resize (scale up) so Tesseract sees bigger text
        scale_percent = 300  # adjust as needed
        width = int(gray.shape[1] * scale_percent / 100)
        height = int(gray.shape[0] * scale_percent / 100)
        gray = cv2.resize(gray, (width, height), interpolation=cv2.INTER_CUBIC)

        # 3) Threshold
        # You can tweak the threshold value or use adaptive threshold
        _, thresh = cv2.threshold(gray, 180, 255, cv2.THRESH_BINARY)

        # (Optional) morphological clean-up
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (1,1))
        thresh = cv2.morphologyEx(thresh, cv2.MORPH_OPEN, kernel, iterations=1)
        thresh = cv2.morphologyEx(thresh, cv2.MORPH_CLOSE, kernel, iterations=1)

        # Convert back to PIL
        processed_image = Image.fromarray(thresh)

        # 4) Tesseract config
        custom_config = r'--psm 6'
        extracted_text = pytesseract.image_to_string(processed_image, lang='eng', config=custom_config)
        lines = extracted_text.splitlines()

        # Debug
        print("DEBUG OCR LINES (after preprocessing):")
        for idx, line in enumerate(lines, start=1):
            print(f"Line {idx}: {repr(line)}")

        roles_to_assign = []
        guild_roles = {role.id: role for role in message.guild.roles}

        for raw_line in lines:
            line = raw_line.strip()
            if not line:
                continue

            # Split into tokens
            tokens = line.split()
            # We expect at least 5 tokens: e.g.
            #   "Aetherian Archive 123,456 ✓ x x ✓"
            # => tokens = ["Aetherian", "Archive", "123,456", "✓", "x", "x", "✓"]
            # The last 4 tokens we interpret as vet/hm1/hm2/hm3 (or possibly there's a number in between).
            if len(tokens) < 5:
                continue

            # The last 4 tokens should be the columns
            maybe_cols = tokens[-4:]  # e.g. ["✓", "x", "x", "✓"]
            # The rest is the trial name plus possibly a score
            maybe_name_tokens = tokens[:-4]

            # We might see a numeric score at the end of the name tokens, so let's
            # remove trailing purely-numeric tokens if present. We'll keep it simple:
            while maybe_name_tokens and re.match(r'^[\d,.\']+$', maybe_name_tokens[-1]):
                maybe_name_tokens.pop()

            # Now whatever remains should be the trial name (fuzzy match it)
            trial_name_candidate = " ".join(maybe_name_tokens)

            # Use difflib to find the best match from self.known_trials
            best_match = difflib.get_close_matches(trial_name_candidate, self.known_trials, n=1, cutoff=0.5)
            # 'cutoff=0.5' means we accept a match if similarity >= 50%. Adjust as needed.

            if not best_match:
                # No fuzzy match found, skip
                continue

            matched_trial = best_match[0]
            # Now parse the columns
            vet_sym, hm1_sym, hm2_sym, hm3_sym = maybe_cols

            vet_checked = vet_sym in self.checkbox_positive
            hm1_checked = hm1_sym in self.checkbox_positive
            hm2_checked = hm2_sym in self.checkbox_positive
            hm3_checked = hm3_sym in self.checkbox_positive

            # Tiered logic
            if hm3_checked:
                # Full HM
                hm_full_role_id = config_py.hm_clears.get(matched_trial)
                if hm_full_role_id:
                    role = guild_roles.get(hm_full_role_id)
                    if role:
                        roles_to_assign.append(role)
            elif hm2_checked:
                # Partial HM (2-boss)
                hm2_role_id = config_py.hm_partial_clears_2_boss.get(matched_trial)
                if hm2_role_id:
                    role = guild_roles.get(hm2_role_id)
                    if role:
                        roles_to_assign.append(role)
            elif hm1_checked:
                # Partial HM (1-boss)
                hm1_role_id = config_py.hm_partial_clears_1_boss.get(matched_trial)
                if hm1_role_id:
                    role = guild_roles.get(hm1_role_id)
                    if role:
                        roles_to_assign.append(role)
            elif vet_checked:
                # Vet
                vet_role_id = config_py.vet_clears.get(matched_trial)
                if vet_role_id:
                    role = guild_roles.get(vet_role_id)
                    if role:
                        roles_to_assign.append(role)

        if not roles_to_assign:
            await message.channel.send(f"{message.author.mention}, no roles detected from this image.")
            return

        # Remove duplicates
        roles_to_assign = list(set(roles_to_assign))

        # Assign all roles
        await message.author.add_roles(*roles_to_assign)

        embed = disnake.Embed(
            title="Assigned Roles",
            description=f"{message.author.mention}, you've been assigned the following roles:",
            color=disnake.Color.green()
        )
        embed.add_field(
            name="Roles",
            value="\n".join(role.name for role in roles_to_assign),
            inline=False
        )

        await message.channel.send(embed=embed)

def setup(bot):
    bot.add_cog(PATRoleAssignerFuzzy(bot))
