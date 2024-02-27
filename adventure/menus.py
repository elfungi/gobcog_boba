from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Tuple, Union
from functools import reduce

import discord
from discord import Interaction
from redbot.core.commands import commands
from redbot.core.i18n import Translator
from redbot.core.utils.chat_formatting import escape, humanize_number
from redbot.vendored.discord.ext import menus

from .bank import bank
from .charsheet import Character
from .constants import Rarities, ANSI_ESCAPE, ANSI_CLOSE, ANSITextColours
from .converters import process_argparse_stat

_ = Translator("Adventure", __file__)
log = logging.getLogger("red.cogs.adventure.menus")

SELL_CONFIRM_AMOUNT = -420


class LeaderboardSource(menus.ListPageSource):
    def __init__(self, entries: List[Tuple[int, Dict]]):
        super().__init__(entries, per_page=10)

    def is_paginating(self):
        return True

    async def format_page(self, menu: menus.MenuPages, entries: List[Tuple[int, Dict]]):
        ctx = menu.ctx
        rebirth_len = len(humanize_number(entries[0][1]["rebirths"]))
        start_position = (menu.current_page * self.per_page) + 1
        pos_len = len(str(start_position + 9)) + 2
        rebirth_len = (len("Rebirths") if len("Rebirths") > rebirth_len else rebirth_len) + 2
        set_piece_len = len("Set Pieces") + 2
        level_len = len("Level") + 2
        header = (
            f"{'#':{pos_len}}{'Rebirths':{rebirth_len}}"
            f"{'Level':{level_len}}{'Set Pieces':{set_piece_len}}{'Adventurer':2}"
        )
        author = ctx.author

        if getattr(ctx, "guild", None):
            guild = ctx.guild
        else:
            guild = None

        players = []
        for position, acc in enumerate(entries, start=start_position):
            user_id = acc[0]
            account_data = acc[1]
            if guild is not None:
                member = guild.get_member(user_id)
            else:
                member = None

            if member is not None:
                username = member.display_name
            else:
                user = menu.ctx.bot.get_user(user_id)
                if user is None:
                    username = f"{user_id}"
                else:
                    username = user.name
            username = escape(username, formatting=True)

            if user_id == author.id:
                # Highlight the author's position
                username = f"<<{username}>>"

            pos_str = position
            rebirths = humanize_number(account_data["rebirths"])
            set_items = humanize_number(account_data["set_items"])
            level = humanize_number(account_data["lvl"])
            data = (
                f"{f'{pos_str}.':{pos_len}}"
                f"{rebirths:{rebirth_len}}"
                f"{level:{level_len}}"
                f"{set_items:{set_piece_len}}"
                f"{username}"
            )
            players.append(data)

        embed = discord.Embed(
            title="Adventure Leaderboard",
            color=await menu.ctx.embed_color(),
            description="```md\n{}``` ```md\n{}```".format(
                header,
                "\n".join(players),
            ),
        )
        embed.set_footer(text=f"Page {menu.current_page + 1}/{self.get_max_pages()}")
        return embed


class WeeklyScoreboardSource(menus.ListPageSource):
    def __init__(self, entries: List[Tuple[int, Dict]], stat: Optional[str] = None):
        super().__init__(entries, per_page=10)
        self._stat = stat or "wins"

    def is_paginating(self):
        return True

    async def format_page(self, menu: menus.MenuPages, entries: List[Tuple[int, Dict]]):
        ctx = menu.ctx
        stats_len = len(humanize_number(entries[0][1][self._stat])) + 3
        start_position = (menu.current_page * self.per_page) + 1
        pos_len = len(str(start_position + 9)) + 2
        stats_plural = self._stat if self._stat.endswith("s") else f"{self._stat}s"
        stats_len = (len(stats_plural) if len(stats_plural) > stats_len else stats_len) + 2
        rebirth_len = len("Rebirths") + 2
        header = f"{'#':{pos_len}}{stats_plural.title().ljust(stats_len)}{'Rebirths':{rebirth_len}}{'Adventurer':2}"
        author = ctx.author

        if getattr(ctx, "guild", None):
            guild = ctx.guild
        else:
            guild = None

        players = []
        for position, (user_id, account_data) in enumerate(entries, start=start_position):
            if guild is not None:
                member = guild.get_member(user_id)
            else:
                member = None

            if member is not None:
                username = member.display_name
            else:
                user = menu.ctx.bot.get_user(user_id)
                if user is None:
                    username = user_id
                else:
                    username = user.name
            username = escape(str(username), formatting=True)
            if user_id == author.id:
                # Highlight the author's position
                username = f"<<{username}>>"

            pos_str = position
            rebirths = humanize_number(account_data["rebirths"])
            stats_value = humanize_number(account_data[self._stat.lower()])

            data = f"{f'{pos_str}.':{pos_len}}" f"{stats_value:{stats_len}}" f"{rebirths:{rebirth_len}}" f"{username}"
            players.append(data)

        embed = discord.Embed(
            title=f"Adventure Weekly Scoreboard",
            color=await menu.ctx.embed_color(),
            description="```md\n{}``` ```md\n{}```".format(
                header,
                "\n".join(players),
            ),
        )
        embed.set_footer(text=f"Page {menu.current_page + 1}/{self.get_max_pages()}")
        return embed


class ScoreboardSource(WeeklyScoreboardSource):
    def __init__(self, entries: List[Tuple[int, Dict]], stat: Optional[str] = None):
        super().__init__(entries)
        self._stat = stat or "wins"
        self._legend = None

    def is_paginating(self):
        return True

    async def format_page(self, menu: menus.MenuPages, entries: List[Tuple[int, Dict]]):
        ctx = menu.ctx
        if self._legend is None:
            self._legend = (
                "React with the following to go to the specified filter:\n"
                "\N{FACE WITH PARTY HORN AND PARTY HAT}: Win scoreboard\n"
                "\N{FIRE}: Loss scoreboard\n"
                "\N{DAGGER KNIFE}: Physical attack scoreboard\n"
                "\N{SPARKLES}: Magic attack scoreboard\n"
                "\N{LEFT SPEECH BUBBLE}: Diplomacy scoreboard\n"
                "\N{PERSON WITH FOLDED HANDS}: Pray scoreboard\n"
                "\N{RUNNER}: Run scoreboard\n"
                "\N{EXCLAMATION QUESTION MARK}: Fumble scoreboard\n"
            )
        stats_len = len(humanize_number(entries[0][1][self._stat])) + 3
        start_position = (menu.current_page * self.per_page) + 1
        pos_len = len(str(start_position + 9)) + 2
        stats_plural = self._stat if self._stat.endswith("s") else f"{self._stat}s"
        stats_len = (len(stats_plural) if len(stats_plural) > stats_len else stats_len) + 2
        rebirth_len = len("Rebirths") + 2
        header = f"{'#':{pos_len}}{stats_plural.title().ljust(stats_len)}{'Rebirths':{rebirth_len}}{'Adventurer':2}"
        author = ctx.author

        if getattr(ctx, "guild", None):
            guild = ctx.guild
        else:
            guild = None

        players = []
        for position, (user_id, account_data) in enumerate(entries, start=start_position):
            if guild is not None:
                member = guild.get_member(user_id)
            else:
                member = None

            if member is not None:
                username = member.display_name
            else:
                user = menu.ctx.bot.get_user(user_id)
                if user is None:
                    username = user_id
                else:
                    username = user.name
            username = escape(str(username), formatting=True)
            if user_id == author.id:
                # Highlight the author's position
                username = f"<<{username}>>"

            pos_str = position
            rebirths = humanize_number(account_data["rebirths"])
            stats_value = humanize_number(account_data[self._stat.lower()])

            data = f"{f'{pos_str}.':{pos_len}}" f"{stats_value:{stats_len}}" f"{rebirths:{rebirth_len}}" f"{username}"
            players.append(data)

        embed = discord.Embed(
            title=f"Adventure {self._stat.title()} Scoreboard",
            color=await menu.ctx.embed_color(),
            description="```md\n{}``` ```md\n{}```".format(
                header,
                "\n".join(players),
            ),
        )
        embed.set_footer(text=f"Page {menu.current_page + 1}/{self.get_max_pages()}")
        return embed


class NVScoreboardSource(WeeklyScoreboardSource):
    def __init__(self, entries: List[Tuple[int, Dict]], stat: Optional[str] = None):
        super().__init__(entries)

    def is_paginating(self):
        return True

    async def format_page(self, menu: menus.MenuPages, entries: List[Tuple[int, Dict]]):
        ctx = menu.ctx
        loses_len = max(len(humanize_number(entries[0][1]["loses"])) + 3, 8)
        win_len = max(len(humanize_number(entries[0][1]["wins"])) + 3, 6)
        xp__len = max(len(humanize_number(entries[0][1]["xp__earnings"])) + 3, 8)
        gold__len = max(len(humanize_number(entries[0][1]["gold__losses"])) + 3, 12)
        start_position = (menu.current_page * self.per_page) + 1
        pos_len = len(str(start_position + 9)) + 2
        header = (
            f"{'#':{pos_len}}{'Wins':{win_len}}"
            f"{'Losses':{loses_len}}{'XP Won':{xp__len}}{'Gold Spent':{gold__len}}{'Adventurer':2}"
        )

        author = ctx.author

        if getattr(ctx, "guild", None):
            guild = ctx.guild
        else:
            guild = None

        players = []
        for position, (user_id, account_data) in enumerate(entries, start=start_position):
            if guild is not None:
                member = guild.get_member(user_id)
            else:
                member = None

            if member is not None:
                username = member.display_name
            else:
                user = menu.ctx.bot.get_user(user_id)
                if user is None:
                    username = user_id
                else:
                    username = user.name

            username = escape(str(username), formatting=True)
            if user_id == author.id:
                # Highlight the author's position
                username = f"<<{username}>>"

            pos_str = position
            loses = humanize_number(account_data["loses"])
            wins = humanize_number(account_data["wins"])
            xp__earnings = humanize_number(account_data["xp__earnings"])
            gold__losses = humanize_number(account_data["gold__losses"])

            data = (
                f"{f'{pos_str}.':{pos_len}} "
                f"{wins:{win_len}} "
                f"{loses:{loses_len}} "
                f"{xp__earnings:{xp__len}} "
                f"{gold__losses:{gold__len}} "
                f"{username}"
            )
            players.append(data)
        msg = "Adventure Negaverse Scoreboard\n```md\n{}``` ```md\n{}``````md\n{}```".format(
            header, "\n".join(players), f"Page {menu.current_page + 1}/{self.get_max_pages()}"
        )
        return msg


class SimpleSource(menus.ListPageSource):
    def __init__(self, entries: List[str, discord.Embed]):
        super().__init__(entries, per_page=1)

    def is_paginating(self):
        return True

    async def format_page(self, menu: menus.MenuPages, page: Union[str, discord.Embed]):
        return page


class EconomySource(menus.ListPageSource):
    def __init__(self, entries: List[Tuple[str, Dict[str, Any]]]):
        super().__init__(entries, per_page=10)
        self._total_balance_unified = None
        self._total_balance_sep = None
        self.author_position = None

    def is_paginating(self):
        return True

    async def format_page(self, menu: menus.MenuPages, entries: List[Tuple[str, Dict[str, Any]]]) -> discord.Embed:
        guild = menu.ctx.guild
        author = menu.ctx.author
        position = (menu.current_page * self.per_page) + 1
        bal_len = len(humanize_number(entries[0][1]["balance"]))
        pound_len = len(str(position + 9))
        user_bal = await bank.get_balance(menu.ctx.author, _forced=not menu.ctx.cog._separate_economy)
        if self.author_position is None:
            self.author_position = await bank.get_leaderboard_position(menu.ctx.author)
        header_primary = "{pound:{pound_len}}{score:{bal_len}}{name:2}\n".format(
            pound="#",
            name=_("Name"),
            score=_("Score"),
            bal_len=bal_len + 6,
            pound_len=pound_len + 3,
        )
        header = ""
        if menu.ctx.cog._separate_economy:
            if self._total_balance_sep is None:
                accounts = await bank._config.all_users()
                overall = 0
                for key, value in accounts.items():
                    overall += value["balance"]
                self._total_balance_sep = overall
            _total_balance = self._total_balance_sep
        else:
            if self._total_balance_unified is None:
                accounts = await bank._get_config(_forced=True).all_users()
                overall = 0
                for key, value in accounts.items():
                    overall += value["balance"]
                self._total_balance_unified = overall
            _total_balance = self._total_balance_unified
        percent = round((int(user_bal) / _total_balance * 100), 3)
        for position, acc in enumerate(entries, start=position):
            user_id = acc[0]
            account_data = acc[1]
            balance = account_data["balance"]
            if guild is not None:
                member = guild.get_member(user_id)
            else:
                member = None
            if member is not None:
                username = member.display_name
            else:
                user = menu.ctx.bot.get_user(user_id)
                if user is None:
                    username = f"{user_id}"
                else:
                    username = user.name
            username = escape(username, formatting=True)
            balance = humanize_number(balance)

            if acc[0] != author.id:
                header += f"{f'{humanize_number(position)}.': <{pound_len + 2}} {balance: <{bal_len + 5}} {username}\n"
            else:
                header += (
                    f"{f'{humanize_number(position)}.': <{pound_len + 2}} "
                    f"{balance: <{bal_len + 5}} "
                    f"<<{username}>>\n"
                )
        if self.author_position is not None:
            embed = discord.Embed(
                title="Adventure Economy Leaderboard\nYou are currently # {}/{}".format(
                    self.author_position, len(self.entries)
                ),
                color=await menu.ctx.embed_color(),
                description="```md\n{}``` ```md\n{}``` ```py\nTotal bank amount {}\nYou have {}% of the total amount!```".format(
                    header_primary, header, humanize_number(_total_balance), percent
                ),
            )
        else:
            embed = discord.Embed(
                title="Adventure Economy Leaderboard\n",
                color=await menu.ctx.embed_color(),
                description="```md\n{}``` ```md\n{}``` ```py\nTotal bank amount {}\nYou have {}% of the total amount!```".format(
                    header_primary, header, humanize_number(_total_balance), percent
                ),
            )
        embed.set_footer(text=f"Page {menu.current_page + 1}/{self.get_max_pages()}")

        return embed


class PrettyBackpackSource(menus.ListPageSource):
    def __init__(self, entries: List[Dict], balance=0, include_sets=True, chests=None, convert_results=None,
                 sold_count=0, sold_price=0, loot_count=0):
        super().__init__(entries, per_page=10)
        self._balance = balance
        self._include_sets = include_sets
        self._chests = chests
        self._convert_results = convert_results
        self._sold_count = sold_count
        self._sold_price = sold_price
        self._items_len = len(entries)
        self._loot_count = loot_count

    def is_paginating(self):
        return True

    async def format_page(self, menu: menus.MenuPages, entries: List[Dict]):
        format_ansi = lambda text, ansi_code=ANSITextColours.white: f"{ANSI_ESCAPE}[{ansi_code}m{text}{ANSI_CLOSE}"
        ctx = menu.ctx
        name_len = 64
        slot_len = 8
        attr_len = 6
        set_len = 28
        author = ctx.author
        start_position = (menu.current_page * self.per_page) + 1

        # START formatting data for item entries
        header = (
            f"{format_ansi('Name'):{name_len}}"  # use ansi on this field to match spacing on table
            f"{'Slot':{slot_len}}"
            f"{'ATT':{attr_len}}"
            f"{'CHA':{attr_len}}"
            f"{'INT':{attr_len}}"
            f"{'DEX':{attr_len}}"
            f"{'LUK':{attr_len}}"
            f"{'QTY':{attr_len}}"
            f"{'DEG':{attr_len}}"
            f"{'LVL':{attr_len}}"
        )
        if self._include_sets:
            header += f"{'  Set':{set_len}}"

        data = []
        for (i, item) in enumerate(entries, start=start_position):
            name = item["name"]
            slot = "2-Hand" if item["slot"] == "Two Handed" else item["slot"]
            level = item["lvl"]
            att = item["att"]
            cha = item["cha"]
            _int = item["int"]
            dex = item["dex"]
            luk = item["luck"]
            owned = item["owned"]
            degrade = item["degrade"]
            _set = item["set"]
            rarity = item["rarity"]
            cannot_equip = item["cannot_equip"]

            deg_value = degrade if rarity in [Rarities.legendary, Rarities.event,
                                              Rarities.ascended] and degrade >= 0 else ""
            set_value = _set if rarity in [Rarities.set] else ""

            ansi_name = rarity.as_ansi(name)
            level_value = format_ansi(level, ANSITextColours.red) if cannot_equip else format_ansi(level)
            i_data = (
                f"{ansi_name:{name_len}}"
                f"{slot:{slot_len}}"
                f"{str(att):{attr_len}}"
                f"{str(cha):{attr_len}}"
                f"{str(_int):{attr_len}}"
                f"{str(dex):{attr_len}}"
                f"{str(luk):{attr_len}}"
                f"{str(owned):{attr_len}}"
                f"{str(deg_value):{attr_len}}"
                f"{level_value:{attr_len}}"
            )
            if self._include_sets:
                i_data += f"     {set_value:{set_len}}"
            data.append(i_data)
        # END formatting data

        # Header
        msg = "```{}'s Backpack - {} gold```".format(author, humanize_number(self._balance))
        msg += "```ansi\n{}```".format(header)

        # START body - this is where the main view is of backpack items
        if self._chests is None or self._loot_count > 0:
            # Item view - either backpack items or opened loot items
            if len(data) == 0:
                no_content = "There doesn't seem to be anything here..."
                msg += "```md\n{}```".format(no_content)
            else:
                msg += "```ansi\n{}``````ansi\n{}```".format(
                    "\n".join(data),
                    f"Page {menu.current_page + 1}/{self.get_max_pages()}"
                )
        else:
            # Loot view - start of view to convert or open chests
            msg += ("```ansi\nYou own {} chests.\n"
                    "\nUse corresponding rarity buttons below to open your chests."
                    "\n"
                    "\nAuto-Convert will convert all your chests in multiples of 25 up to Legendary.```"
                    .format(self._chests))
        # END body

        # Start contextual message
        if self._sold_count > 0:
            # Items sold
            msg += "```md\n* {} item(s) sold for {}.```".format(
                self._sold_count,
                humanize_number(self._sold_price)
            )
        elif self._sold_count == -1:
            # Tried to sell item but in adventure
            msg += "```md\nYou tried to go sell your items but the monster ahead is not allowing you to leave.```"
        elif self._sold_count == SELL_CONFIRM_AMOUNT:
            # Confirmation needed for selling
            msg += (
                "```md\n* Are you sure you want to sell these {} listings and their copies? Press the confirm button to proceed.```"
                .format(
                    humanize_number(self._items_len)
                ))
        elif self._convert_results is not None:
            # Doing auto-convert
            if len(self._convert_results.keys()) == 0:
                # Tried to auto-convert but in adventure
                msg += "```md\n* You tried to go convert your loot but the monster ahead is not allowing you to leave.```"
            elif reduce(lambda a, b: a + b, self._convert_results.values()) == 0:
                # Tried to auto-convert but nothing was converted
                msg += "```md\n* You tried to go convert your loot but you're a bit short on chests to upgrade.```"
            else:
                # Successful convert
                msg += "```md\n* Successfully converted into"
                normal = " {} Rare".format(self._convert_results["normal"]) if self._convert_results[
                                                                                   "normal"] > 0 else ""
                rare = " {} Epic".format(self._convert_results["rare"]) if self._convert_results["rare"] > 0 else ""
                epic = " {} Legendary".format(self._convert_results["epic"]) if self._convert_results[
                                                                                    "epic"] > 0 else ""
                msg += ",".join(filter(None, [normal, rare, epic]))
                msg += " chest(s).```"
        elif self._loot_count > 0:
            # Opened chests
            if self._items_len == 0:
                # Tried to open chests but in adventure or backpack is full
                msg += "```md\n* You tried to go open your loot but you're either occupied or your backpack is full.```"
            else:
                # Chests opened successful
                msg += ("```ansi\nYou own {} chests.```".format(self._chests))
        return msg


class StopButton(discord.ui.Button):
    def __init__(
            self,
            style: discord.ButtonStyle,
            row: Optional[int] = None,
    ):
        super().__init__(style=style, row=row)
        self.style = style
        self.emoji = "\N{HEAVY MULTIPLICATION X}\N{VARIATION SELECTOR-16}"

    async def callback(self, interaction: discord.Interaction):
        self.view.stop()
        if interaction.message.flags.ephemeral:
            await interaction.response.edit_message(view=None)
            return
        await interaction.message.delete()


class _NavigateButton(discord.ui.Button):
    def __init__(self, style: discord.ButtonStyle, emoji: Union[str, discord.PartialEmoji], direction: int):
        super().__init__(style=style, emoji=emoji)
        self.direction = direction

    async def callback(self, interaction: discord.Interaction):
        if self.direction == 0:
            self.view.current_page = 0
        elif self.direction == self.view.source.get_max_pages():
            self.view.current_page = self.view.source.get_max_pages() - 1
        else:
            self.view.current_page += self.direction
        try:
            page = await self.view.source.get_page(self.view.current_page)
        except IndexError:
            self.view.current_page = 0
            page = await self.view.source.get_page(self.view.current_page)
        kwargs = await self.view._get_kwargs_from_page(page)
        await interaction.response.edit_message(**kwargs)


class BaseMenu(discord.ui.View):
    def __init__(
            self,
            source: menus.PageSource,
            clear_reactions_after: bool = True,
            delete_message_after: bool = False,
            timeout: int = 180,
            message: discord.Message = None,
            **kwargs: Any,
    ) -> None:
        super().__init__(timeout=timeout)
        self._source = source
        self.page_start = kwargs.get("page_start", 0)
        self.current_page = self.page_start
        self.message = message
        self.forward_button = _NavigateButton(
            discord.ButtonStyle.grey,
            "\N{BLACK RIGHT-POINTING TRIANGLE}\N{VARIATION SELECTOR-16}",
            direction=1,
        )
        self.backward_button = _NavigateButton(
            discord.ButtonStyle.grey,
            "\N{BLACK LEFT-POINTING TRIANGLE}\N{VARIATION SELECTOR-16}",
            direction=-1,
        )
        self.first_button = _NavigateButton(
            discord.ButtonStyle.grey,
            "\N{BLACK LEFT-POINTING DOUBLE TRIANGLE WITH VERTICAL BAR}\N{VARIATION SELECTOR-16}",
            direction=0,
        )
        self.last_button = _NavigateButton(
            discord.ButtonStyle.grey,
            "\N{BLACK RIGHT-POINTING DOUBLE TRIANGLE WITH VERTICAL BAR}\N{VARIATION SELECTOR-16}",
            direction=self.source.get_max_pages(),
        )
        self.stop_button = StopButton(discord.ButtonStyle.red)
        self.add_item(self.stop_button)
        if self.source.is_paginating():
            self.add_item(self.first_button)
            self.add_item(self.backward_button)
            self.add_item(self.forward_button)
            self.add_item(self.last_button)

    async def on_timeout(self):
        if self.message is not None:
            await self.message.edit(view=None)

    @property
    def source(self):
        return self._source

    async def change_source(self, source: menus.PageSource, interaction: discord.Interaction):
        self._source = source
        self.current_page = 0
        if self.message is not None:
            await source._prepare_once()
            await self.show_page(0, interaction)

    async def update(self):
        """
        Define this here so that subclasses can utilize this hook
        and update the state of the view before sending.
        This is useful for modifying disabled buttons etc.

        This gets called after the page has been formatted.
        """
        pass

    async def start(
            self,
            ctx: Optional[commands.Context],
            *,
            wait=False,
            page: int = 0,
            interaction: Optional[discord.Interaction] = None,
    ):
        """
        Starts the interactive menu session.

        Parameters
        -----------
        ctx: :class:`Context`
            The invocation context to use.
        channel: :class:`discord.abc.Messageable`
            The messageable to send the message to. If not given
            then it defaults to the channel in the context.
        wait: :class:`bool`
            Whether to wait until the menu is completed before
            returning back to the caller.

        Raises
        -------
        MenuError
            An error happened when verifying permissions.
        discord.HTTPException
            Adding a reaction failed.
        """

        if ctx is not None:
            self.bot = ctx.bot
            self._author_id = ctx.author.id
        elif interaction is not None:
            self.bot = interaction.client
            self._author_id = interaction.user.id
        self.ctx = ctx
        msg = self.message
        if msg is None:
            self.message = await self.send_initial_message(ctx, page=page, interaction=interaction)
        if wait:
            return await self.wait()

    async def _get_kwargs_from_page(self, page: Any):
        value = await self.source.format_page(self, page)
        if isinstance(value, dict):
            return value
        elif isinstance(value, str):
            return {"content": value, "embed": None}
        elif isinstance(value, discord.Embed):
            return {"embed": value, "content": None}
        return value

    async def show_page(self, page_number: int, interaction: discord.Interaction):
        page = await self.source.get_page(page_number)
        self.current_page = page_number
        kwargs = await self._get_kwargs_from_page(page)
        await self.update()
        await interaction.response.edit_message(**kwargs, view=self)

    async def send_initial_message(
            self, ctx: Optional[commands.Context], page: int = 0, interaction: Optional[discord.Interaction] = None
    ):
        """

        The default implementation of :meth:`Menu.send_initial_message`
        for the interactive pagination session.

        This implementation shows the first page of the source.
        """
        self.current_page = page
        page = await self._source.get_page(page)
        kwargs = await self._get_kwargs_from_page(page)
        await self.update()
        if ctx is None and interaction is not None:
            await interaction.response.send_message(**kwargs, view=self)
            return await interaction.original_response()
        else:
            return await ctx.send(**kwargs, view=self)

    async def show_checked_page(self, page_number: int, interaction: discord.Interaction) -> None:
        max_pages = self._source.get_max_pages()
        try:
            if max_pages is None:
                # If it doesn't give maximum pages, it cannot be checked
                await self.show_page(page_number, interaction)
            elif page_number >= max_pages:
                await self.show_page(0, interaction)
            elif page_number < 0:
                await self.show_page(max_pages - 1, interaction)
            elif max_pages > page_number >= 0:
                await self.show_page(page_number, interaction)
        except IndexError:
            # An error happened that can be handled, so ignore it.
            pass

    async def interaction_check(self, interaction: discord.Interaction):
        if interaction.user.id not in (*interaction.client.owner_ids, self._author_id):
            await interaction.response.send_message(_("You are not authorized to interact with this."), ephemeral=True)
            return False
        return True


class ScoreBoardMenu(BaseMenu):
    def __init__(
            self,
            source: menus.PageSource,
            cog: Optional[commands.Cog] = None,
            clear_reactions_after: bool = True,
            delete_message_after: bool = False,
            timeout: int = 180,
            message: discord.Message = None,
            show_global: bool = False,
            current_scoreboard: str = "wins",
            **kwargs: Any,
    ) -> None:
        super().__init__(
            source=source,
            clear_reactions_after=clear_reactions_after,
            delete_message_after=delete_message_after,
            timeout=timeout,
            message=message,
            **kwargs,
        )
        self.cog = cog
        self.show_global = show_global
        self._current = current_scoreboard

    async def update(self):
        buttons = {
            "wins": self.wins,
            "loses": self.losses,
            "fight": self.physical,
            "spell": self.magic,
            "talk": self.diplomacy,
            "pray": self.praying,
            "run": self.runner,
            "fumbles": self.fumble,
        }
        for button in buttons.values():
            button.disabled = False
        buttons[self._current].disabled = True

    @discord.ui.button(
        label=_("Wins"),
        style=discord.ButtonStyle.grey,
        emoji="\N{FACE WITH PARTY HORN AND PARTY HAT}",
        row=1,
        disabled=True,
    )
    async def wins(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        if self._current == "wins":
            await interaction.response.defer()
            # this deferal is unnecessary now since the buttons are just disabled
            # however, in the event that the button gets passed and the state is not
            # as we expect at least try not to send the user an interaction failed message
            return
        self._current = "wins"
        rebirth_sorted = await self.cog.get_global_scoreboard(
            guild=self.ctx.guild if not self.show_global else None, keyword=self._current
        )
        await self.change_source(
            source=ScoreboardSource(entries=rebirth_sorted, stat=self._current), interaction=interaction
        )

    @discord.ui.button(label=_("Losses"), style=discord.ButtonStyle.grey, emoji="\N{FIRE}", row=1)
    async def losses(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        if self._current == "loses":
            await interaction.response.defer()
            return
        self._current = "loses"
        rebirth_sorted = await self.cog.get_global_scoreboard(
            guild=self.ctx.guild if not self.show_global else None, keyword=self._current
        )
        await self.change_source(
            source=ScoreboardSource(entries=rebirth_sorted, stat=self._current), interaction=interaction
        )

    @discord.ui.button(label=_("Physical"), style=discord.ButtonStyle.grey, emoji="\N{DAGGER KNIFE}", row=1)
    async def physical(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        """stops the pagination session."""
        if self._current == "fight":
            await interaction.response.defer()
            return
        self._current = "fight"
        rebirth_sorted = await self.cog.get_global_scoreboard(
            guild=self.ctx.guild if not self.show_global else None, keyword=self._current
        )
        await self.change_source(
            source=ScoreboardSource(entries=rebirth_sorted, stat=self._current), interaction=interaction
        )

    @discord.ui.button(label=_("Magic"), style=discord.ButtonStyle.grey, emoji="\N{SPARKLES}", row=1)
    async def magic(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        if self._current == "spell":
            await interaction.response.defer()
            return
        self._current = "spell"
        rebirth_sorted = await self.cog.get_global_scoreboard(
            guild=self.ctx.guild if not self.show_global else None, keyword=self._current
        )
        await self.change_source(
            source=ScoreboardSource(entries=rebirth_sorted, stat=self._current), interaction=interaction
        )

    @discord.ui.button(label=_("Charisma"), style=discord.ButtonStyle.grey, emoji="\N{LEFT SPEECH BUBBLE}", row=1)
    async def diplomacy(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        if self._current == "talk":
            await interaction.response.defer()
            return
        self._current = "talk"
        rebirth_sorted = await self.cog.get_global_scoreboard(
            guild=self.ctx.guild if not self.show_global else None, keyword=self._current
        )
        await self.change_source(
            source=ScoreboardSource(entries=rebirth_sorted, stat=self._current), interaction=interaction
        )

    @discord.ui.button(label=_("Pray"), style=discord.ButtonStyle.grey, emoji="\N{PERSON WITH FOLDED HANDS}", row=2)
    async def praying(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        if self._current == "pray":
            await interaction.response.defer()
            return
        self._current = "pray"
        rebirth_sorted = await self.cog.get_global_scoreboard(
            guild=self.ctx.guild if not self.show_global else None, keyword=self._current
        )
        await self.change_source(
            source=ScoreboardSource(entries=rebirth_sorted, stat=self._current), interaction=interaction
        )

    @discord.ui.button(label=_("Run"), style=discord.ButtonStyle.grey, emoji="\N{RUNNER}", row=2)
    async def runner(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        if self._current == "run":
            await interaction.response.defer()
            return
        self._current = "run"
        rebirth_sorted = await self.cog.get_global_scoreboard(
            guild=self.ctx.guild if not self.show_global else None, keyword=self._current
        )
        await self.change_source(
            source=ScoreboardSource(entries=rebirth_sorted, stat=self._current), interaction=interaction
        )

    @discord.ui.button(label=_("Fumbles"), style=discord.ButtonStyle.grey, emoji="\N{EXCLAMATION QUESTION MARK}", row=2)
    async def fumble(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        if self._current == "fumbles":
            await interaction.response.defer()
            return
        self._current = "fumbles"
        rebirth_sorted = await self.cog.get_global_scoreboard(
            guild=self.ctx.guild if not self.show_global else None, keyword=self._current
        )
        await self.change_source(
            source=ScoreboardSource(entries=rebirth_sorted, stat=self._current), interaction=interaction
        )


class LeaderboardMenu(BaseMenu):
    def __init__(
            self,
            source: menus.PageSource,
            cog: Optional[commands.Cog] = None,
            clear_reactions_after: bool = True,
            delete_message_after: bool = False,
            timeout: int = 180,
            message: discord.Message = None,
            show_global: bool = False,
            current_scoreboard: str = "leaderboard",
            **kwargs: Any,
    ) -> None:
        super().__init__(
            source,
            clear_reactions_after=clear_reactions_after,
            delete_message_after=delete_message_after,
            timeout=timeout,
            message=message,
            **kwargs,
        )
        self.cog = cog
        self.show_global = show_global
        self._current = current_scoreboard

    async def update(self):
        buttons = {"leaderboard": self.home, "economy": self.economy}
        for button in buttons.values():
            button.disabled = False
        buttons[self._current].disabled = True

    def _unified_bank(self):
        return not self.cog._separate_economy

    @discord.ui.button(
        label=_("Leaderboard"),
        style=discord.ButtonStyle.grey,
        emoji="\N{CHART WITH UPWARDS TREND}",
        row=1,
        disabled=True,
    )
    async def home(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        if self._current == "leaderboard":
            await interaction.response.defer()
            return
        self._current = "leaderboard"
        rebirth_sorted = await self.cog.get_leaderboard(guild=self.ctx.guild if not self.show_global else None)
        await self.change_source(source=LeaderboardSource(entries=rebirth_sorted), interaction=interaction)

    @discord.ui.button(label=_("Economy"), style=discord.ButtonStyle.grey, emoji="\N{MONEY WITH WINGS}", row=1)
    async def economy(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        if self._current == "economy":
            await interaction.response.defer()
            return
        self._current = "economy"
        bank_sorted = await bank.get_leaderboard(
            guild=self.ctx.guild if not self.show_global else None, _forced=self._unified_bank()
        )
        await self.change_source(source=EconomySource(entries=bank_sorted), interaction=interaction)


class BackpackMenu(BaseMenu):
    def __init__(
            self,
            source: menus.PageSource,
            help_command: commands.Command,
            clear_reactions_after: bool = True,
            delete_message_after: bool = False,
            timeout: int = 180,
            message: discord.Message = None,
            **kwargs: Any,
    ) -> None:
        super().__init__(
            source,
            clear_reactions_after=clear_reactions_after,
            delete_message_after=delete_message_after,
            timeout=timeout,
            message=message,
            **kwargs,
        )
        self.__help_command = help_command

    @discord.ui.button(style=discord.ButtonStyle.grey, emoji="\N{INFORMATION SOURCE}\N{VARIATION SELECTOR-16}", row=1)
    async def send_help(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        """Sends help for the provided command."""
        await self.ctx.send_help(self.__help_command)
        self.delete_message_after = True
        self.stop()
        await interaction.response.defer()
        await self.on_timeout()


class InteractiveBackpackMenu(BaseMenu):
    def __init__(
            self,
            source,
            c: Character,
            sell_callback: Any,
            convert_callback: Any,
            open_loot_callback: Any,
            auto_toggle_callback: Any,
            clear_reactions_after: bool = True,
            delete_message_after: bool = False,
            timeout: int = 180,
            message: discord.Message = None,
            **kwargs: Any
    ) -> None:
        super().__init__(
            source=source,
            clear_reactions_after=clear_reactions_after,
            delete_message_after=delete_message_after,
            timeout=timeout,
            message=message,
            **kwargs
        )
        self._c = c
        self._sell_callback = sell_callback
        self._convert_callback = convert_callback
        self._open_loot_callback = open_loot_callback
        self._auto_toggle_callback = auto_toggle_callback
        self._current_view = ""
        self._rarities = []
        self._stats = self.initial_stats_filters()
        self._equippable = False
        self._delta = False
        self._sold_count = 0
        self._sold_price = 0
        self._convert_results = None
        self._search_text = ""
        self.initial_state()
        # remove useless buttons from parents
        self.remove_item(self.stop_button)
        self.remove_item(self.last_button)
        self.remove_item(self.first_button)
        self.remove_item(self.forward_button)
        self.remove_item(self.backward_button)

    def initial_state(self):
        self._current_view = "default"
        self._rarities = [i for i in Rarities]
        self._stats = self.initial_stats_filters()
        self._equippable = False
        self._delta = False
        self._sold_count = 0
        self._sold_price = 0
        self._convert_results = None
        self._search_text = ""

    def initial_stats_filters(self):
        return {
            'att': None,
            'cha': None,
            'int': None,
            'dex': None,
            'luk': None,
            'deg': None,
            'lvl': None
        }

    def highlight_stats_filter_button(self, button, attrs):
        if self._current_view == "loot":
            button.style = discord.ButtonStyle.grey
            button.disabled = True
            return False
        else:
            button.disabled = False
            selected = False
            for i in attrs:
                if self._stats[i] is not None:
                    button.style = discord.ButtonStyle.green
                    selected = True
                    break
            if not selected:
                button.style = discord.ButtonStyle.grey
            return selected

    async def update(self):
        view_buttons = {
            "default": self.default_button,
            "can_equip": self.can_equip_button,
            "loot": self.loot_button
        }
        for button in view_buttons.values():
            button.disabled = False
        view_buttons[self._current_view].disabled = True
        loot_view = self._current_view == "loot"

        rarity_buttons = {
            Rarities.rare: self.rare_filter,
            Rarities.epic: self.epic_filter,
            Rarities.legendary: self.legendary_filter,
            Rarities.ascended: self.ascended_filter,
            Rarities.set: self.set_filter
        }

        rarity_enabled = False
        for r in [Rarities.rare, Rarities.epic, Rarities.legendary, Rarities.ascended, Rarities.set]:
            if loot_view:
                if self._c.treasure[r.value] > 0:
                    rarity_buttons[r].style = discord.ButtonStyle.green
                    rarity_buttons[r].disabled = False
                else:
                    rarity_buttons[r].style = discord.ButtonStyle.grey
                    rarity_buttons[r].disabled = True
            else:
                rarity_buttons[r].disabled = False
                if r in self._rarities:
                    rarity_buttons[r].style = discord.ButtonStyle.green
                    rarity_enabled = True
                else:
                    rarity_buttons[r].style = discord.ButtonStyle.grey

        if not rarity_enabled or loot_view:
            self.clear_rarity.disabled = True
            self.clear_rarity.style = discord.ButtonStyle.grey
        else:
            self.clear_rarity.disabled = False
            self.clear_rarity.style = discord.ButtonStyle.red

        filter_selected = self.highlight_stats_filter_button(self.filter_group_1, ['att', 'cha', 'int', 'dex', 'luk'])
        filter_selected = filter_selected or self.highlight_stats_filter_button(self.filter_group_2, ['deg', 'lvl'])
        if len(self._search_text) > 0 and not loot_view:
            self.search_button.style = discord.ButtonStyle.green
            filter_selected = True
        else:
            self.search_button.style = discord.ButtonStyle.grey
        self.search_button.disabled = loot_view

        if not filter_selected or loot_view:
            self.clear_filters.disabled = True
            self.clear_filters.style = discord.ButtonStyle.grey
        else:
            self.clear_filters.disabled = False
            self.clear_filters.style = discord.ButtonStyle.red

        if self._c.do_not_disturb:
            self.auto_toggle.label = "Turn Auto-Battle On \u200b"
            self.auto_toggle.style = discord.ButtonStyle.red
        else:
            self.auto_toggle.label = "Turn Auto-Battle Off"
            self.auto_toggle.style = discord.ButtonStyle.green

        self.update_contextual_button()

    def update_contextual_button(self):
        label_space_pre = "\u200b "
        label_space_post = " \u200b"
        sell_all_label = str(label_space_pre * 7) + "Sell All" + str(label_space_post * 8)
        confirm_sell_label = str(label_space_pre * 6) + "Confirm Sell" + str(label_space_post * 6)
        auto_convert_label = str(label_space_pre * 5) + "Auto-Convert" + str(label_space_post * 4)

        if self._current_view != "loot":
            if self._sold_count == SELL_CONFIRM_AMOUNT:
                # sell all confirm
                self.contextual_button.emoji = None
                self.contextual_button.label = confirm_sell_label
                self.contextual_button.style = discord.ButtonStyle.red
            else:
                # sell all enabled
                self.contextual_button.emoji = "\N{COIN}"
                self.contextual_button.label = sell_all_label
                self.contextual_button.style = discord.ButtonStyle.red
        else:
            self.contextual_button.emoji = None
            self.contextual_button.label = auto_convert_label
            self.contextual_button.style = discord.ButtonStyle.green

    @discord.ui.button(style=discord.ButtonStyle.red, emoji="\N{HEAVY MULTIPLICATION X}\N{VARIATION SELECTOR-16}",
                       row=0)
    async def _stop_button(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        button.view.stop()
        if interaction.message.flags.ephemeral:
            await interaction.response.edit_message(view=None)
            return
        await interaction.message.delete()

    @discord.ui.button(style=discord.ButtonStyle.grey,
                       emoji="\N{BLACK LEFT-POINTING TRIANGLE}\N{VARIATION SELECTOR-16}", row=0)
    async def _back_button(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        button.view.current_page -= 1 if button.view.current_page > 0 else 0
        await self.navigate_page(interaction, button)

    @discord.ui.button(style=discord.ButtonStyle.grey,
                       emoji="\N{BLACK RIGHT-POINTING TRIANGLE}\N{VARIATION SELECTOR-16}", row=0)
    async def _forward_button(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        max_pages = self.source.get_max_pages()
        if button.view.current_page + 1 < max_pages:
            button.view.current_page += 1
        await self.navigate_page(interaction, button)

    @discord.ui.button(style=discord.ButtonStyle.grey, label="Contextual Button", row=0)
    async def contextual_button(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        if self._current_view != "loot":
            if self._sold_count == SELL_CONFIRM_AMOUNT:
                # confirm action
                backpack_items = await self.get_backpack_item_for_sell()
                count, amount = await self._sell_callback(self.ctx, self._c, backpack_items)
                self._sold_count = count
                self._sold_price = amount
                await self.do_change_source(interaction)
            else:
                # start confirm action
                self._sold_count = SELL_CONFIRM_AMOUNT
                await self.do_change_source(interaction)
        else:
            # auto-convert button
            self._convert_results = await self._convert_callback(self.ctx, self._c)
            await self.do_change_source(interaction)

    @discord.ui.button(style=discord.ButtonStyle.red, label="Auto Toggle", row=0)
    async def auto_toggle(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        self._c = await self._auto_toggle_callback(self.ctx, self._c)
        await self.do_change_source(interaction)

    @discord.ui.button(style=discord.ButtonStyle.primary,
                       label="\u200b \u200b \u200b \u200b \u200b \u200b \u200b \u200b Backpack\u200b \u200b \u200b \u200b \u200b \u200b \u200b \u200b",
                       row=1)
    async def default_button(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        self._current_view = "default"
        self._equippable = False
        self._delta = False
        self.reset_contextual_state()
        await self.do_change_source(interaction)

    @discord.ui.button(style=discord.ButtonStyle.primary,
                       label="Loot",
                       row=1)
    async def loot_button(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        self._current_view = "loot"
        self.reset_contextual_state()
        await self.do_change_source(interaction)

    @discord.ui.button(style=discord.ButtonStyle.primary, label="\u200b \u200b Equipable \u200b \u200b \u200b", row=1)
    async def can_equip_button(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        self._current_view = "can_equip"
        self._equippable = True
        self._delta = True
        self.reset_contextual_state()
        await self.do_change_source(interaction)

    @discord.ui.button(style=discord.ButtonStyle.red,
                       label="\u200b \u200b \u200b \u200b Reset \u200b \u200b \u200b \u200b ", row=1)
    async def reset_button(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        self.initial_state()
        await self.do_change_source(interaction)

    @discord.ui.button(style=discord.ButtonStyle.green,
                       label="\u200b \u200b \u200b Normal + Rare \u200b \u200b \u200b ", row=2)
    async def rare_filter(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        if self._current_view == "loot":
            title = "Can't open Normal, sorry. Enter # for Rare."
            modal = InteractiveBackpackLootModal(self, self.ctx, "rare", self._c.treasure["rare"].number, title)
            await interaction.response.send_modal(modal)
        else:
            self.update_rarities(Rarities.normal)
            self.update_rarities(Rarities.rare)
            await self.do_change_source(interaction)

    @discord.ui.button(style=discord.ButtonStyle.green, label="Epic", row=2)
    async def epic_filter(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        if self._current_view == "loot":
            modal = InteractiveBackpackLootModal(self, self.ctx, "epic", self._c.treasure["epic"].number)
            await interaction.response.send_modal(modal)
        else:
            self.update_rarities(Rarities.epic)
            await self.do_change_source(interaction)

    @discord.ui.button(style=discord.ButtonStyle.green, label="\u200b \u200b Legendary \u200b \u200b", row=2)
    async def legendary_filter(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        if self._current_view == "loot":
            modal = InteractiveBackpackLootModal(self, self.ctx, "legendary", self._c.treasure["legendary"].number)
            await interaction.response.send_modal(modal)
        else:
            self.update_rarities(Rarities.legendary)
            await self.do_change_source(interaction)

    @discord.ui.button(style=discord.ButtonStyle.green, label="Ascended", row=2)
    async def ascended_filter(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        if self._current_view == "loot":
            modal = InteractiveBackpackLootModal(self, self.ctx, "ascended", self._c.treasure["ascended"].number)
            await interaction.response.send_modal(modal)
        else:
            self.update_rarities(Rarities.ascended)
            await self.do_change_source(interaction)

    @discord.ui.button(style=discord.ButtonStyle.green,
                       label="\u200b \u200b \u200b \u200b \u200b \u200b \u200b Set \u200b \u200b \u200b \u200b \u200b \u200b",
                       row=2)
    async def set_filter(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        if self._current_view == "loot":
            modal = InteractiveBackpackLootModal(self, self.ctx, "set", self._c.treasure["set"].number)
            await interaction.response.send_modal(modal)
        else:
            self.update_rarities(Rarities.set)
            await self.do_change_source(interaction)

    @discord.ui.button(style=discord.ButtonStyle.primary,
                       label="\u200b Search By Name \u200b",
                       row=3)
    async def search_button(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        modal = InteractiveBackpackSearchModal(self, self.ctx)
        await interaction.response.send_modal(modal)

    @discord.ui.button(style=discord.ButtonStyle.grey,
                       label="Stats",
                       row=3)
    async def filter_group_1(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        input_mapping = {key: self._stats[key] for key in self._stats.keys() & {'att', 'cha', 'int', 'dex', 'luk'}}
        modal = InteractiveBackpackFilterModal(self, self.ctx, "Stats Filters Group 1", input_mapping)
        await interaction.response.send_modal(modal)

    @discord.ui.button(style=discord.ButtonStyle.grey,
                       label="\u200b \u200b \u200b \u200b \u200b Deg/Lvl \u200b \u200b \u200b \u200b",
                       row=3)
    async def filter_group_2(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        input_mapping = {key: self._stats[key] for key in self._stats.keys() & {'deg', 'lvl'}}
        modal = InteractiveBackpackFilterModal(self, self.ctx, "Stats Filters Group 2", input_mapping)
        await interaction.response.send_modal(modal)

    @discord.ui.button(style=discord.ButtonStyle.red, emoji="\N{HEAVY MULTIPLICATION X}\N{VARIATION SELECTOR-16}",
                       label="Rarity", row=3)
    async def clear_rarity(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        self._rarities = [Rarities.pet]  # cheat here and use a rarity we don't have to filter
        self.reset_contextual_state()
        await self.do_change_source(interaction)

    @discord.ui.button(style=discord.ButtonStyle.red, emoji="\N{HEAVY MULTIPLICATION X}\N{VARIATION SELECTOR-16}",
                       label="Filters", row=3)
    async def clear_filters(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        self._stats = self.initial_stats_filters()
        self._search_text = ""
        self.reset_contextual_state()
        await self.do_change_source(interaction)

    def update_rarities(self, rarity):
        self.reset_contextual_state()
        if rarity in self._rarities:
            self._rarities.remove(rarity)
        else:
            self._rarities.append(rarity)

    def reset_contextual_state(self):
        self._sold_count = 0
        self._sold_price = 0
        self._convert_results = None

    async def get_backpack_item_for_sell(self):
        return await self.get_backpack_items(True)

    def get_filter_attr(self, attr):
        value = self._stats[attr]
        if value is not None:
            return process_argparse_stat(self._stats, attr)[attr]
        else:
            return None

    def set_stat_filter(self, attr, value):
        if value:
            self._stats[attr] = [value]
        else:
            self._stats[attr] = None

    async def get_backpack_items(self, for_sell=False):
        att_filter = self.get_filter_attr('att')
        cha_filter = self.get_filter_attr('cha')
        int_filter = self.get_filter_attr('int')
        dex_filter = self.get_filter_attr('dex')
        luk_filter = self.get_filter_attr('luk')
        deg_filter = self.get_filter_attr('deg')
        lvl_filter = self.get_filter_attr('lvl')
        if for_sell:
            return await self._c.get_argparse_backpack_no_format_items(rarities=self._rarities,
                                                                       equippable=self._equippable,
                                                                       delta=self._delta,
                                                                       match=self._search_text,
                                                                       strength=att_filter,
                                                                       charisma=cha_filter,
                                                                       intelligence=int_filter,
                                                                       dexterity=dex_filter,
                                                                       luck=luk_filter,
                                                                       degrade=deg_filter,
                                                                       level=lvl_filter)
        else:
            return await self._c.get_argparse_backpack_no_format(rarities=self._rarities,
                                                                 equippable=self._equippable,
                                                                 delta=self._delta,
                                                                 match=self._search_text,
                                                                 strength=att_filter,
                                                                 charisma=cha_filter,
                                                                 intelligence=int_filter,
                                                                 dexterity=dex_filter,
                                                                 luck=luk_filter,
                                                                 degrade=deg_filter,
                                                                 level=lvl_filter)

    async def do_change_source(self, interaction, items=None, loot_count=0):
        balance = self._c.get_higher_balance()
        backpack_items = await self.get_backpack_items() if items is None else items
        include_sets = Rarities.set in self._rarities or self._current_view == "loot"
        chests = self._c.treasure.ansi if self._current_view == "loot" else None
        await self.change_source(
            source=PrettyBackpackSource(backpack_items, balance, include_sets, chests, self._convert_results,
                                        self._sold_count, self._sold_price, loot_count),
            interaction=interaction)

    async def do_change_source_from_search(self, interaction):
        self._current_view = "search"
        self._equippable = False
        self._delta = False
        self.reset_contextual_state()
        await self.do_change_source(interaction)

    async def do_open_loot(self, interaction, rarity, number):
        self._convert_results = None  # reset convert results whenever loot is opened
        opened_items = await self._open_loot_callback(self.ctx, self._c, rarity, number)
        await self.do_change_source(interaction, opened_items, number)

    async def navigate_page(self, interaction, button):
        try:
            page = await button.view.source.get_page(button.view.current_page)
        except IndexError:
            button.view.current_page = 0
            page = await button.view.source.get_page(button.view.current_page)
        kwargs = await button.view._get_kwargs_from_page(page)
        await interaction.response.edit_message(**kwargs)

    @property
    def search_text(self):
        return self._search_text


class InteractiveBackpackFilterModal(discord.ui.Modal):
    def __init__(self, backpack_menu: InteractiveBackpackMenu, ctx: commands.Context, title,
                 input_mapping: Dict[str, str]):
        super().__init__(title=title)
        self.ctx = ctx
        self.backpack_menu = backpack_menu
        self.keys = []
        self.build_inputs(input_mapping)

    def build_inputs(self, input_mapping):
        keys = []
        for (key, value) in input_mapping.items():
            built_input = self.build_input(key.upper(), value)
            item = {'value': value, 'input': built_input}
            self.__setattr__(key, item)
            keys.append(key)
            self.add_item(built_input)
        self.keys = keys

    async def on_submit(self, interaction: discord.Interaction):
        for key in self.keys:
            item = self.__getattribute__(key)
            value = item['input'].value
            self.backpack_menu.set_stat_filter(key, value)
        self.backpack_menu.reset_contextual_state()
        await self.backpack_menu.do_change_source(interaction)

    def build_input(self, label, value):
        v = value[0] if value and len(value) > 0 else None
        return discord.ui.TextInput(
            label=label,
            placeholder="e.g. >10, <100",
            default=v,
            style=discord.TextStyle.short,
            max_length=20,
            min_length=0,
            required=False
        )


class InteractiveBackpackSearchModal(discord.ui.Modal):
    def __init__(self, backpack_menu: InteractiveBackpackMenu, ctx: commands.Context):
        super().__init__(title='Backpack Search')
        self.ctx = ctx
        self.backpack_menu = backpack_menu
        self.search_input = self.build_input(backpack_menu.search_text)
        self.add_item(self.search_input)

    async def on_submit(self, interaction: discord.Interaction):
        self.backpack_menu._search_text = self.search_input.value
        self.backpack_menu.reset_contextual_state()
        await self.backpack_menu.do_change_source(interaction)

    def build_input(self, value):
        return discord.ui.TextInput(
            label="Search by name (case insensitive)",
            default=value,
            style=discord.TextStyle.short,
            max_length=100,
            min_length=0,
            required=False
        )


class InteractiveBackpackLootModal(discord.ui.Modal):
    def __init__(self, backpack_menu: InteractiveBackpackMenu, ctx: commands.Context, rarity, max_value, title=None):
        actual_title = "How many {} chests to open?".format(rarity) if title is None else title
        super().__init__(title=actual_title)
        self.ctx = ctx
        self.backpack_menu = backpack_menu
        self.rarity = rarity
        self.max_value = max_value
        self.loot_input = self.build_input()
        self.add_item(self.loot_input)

    async def on_submit(self, interaction: discord.Interaction):
        await self.backpack_menu.do_open_loot(interaction, self.rarity, int(self.loot_input.value))

    async def interaction_check(self, interaction: Interaction, /) -> bool:
        if int(self.loot_input.value) < 1 or int(self.loot_input.value) > min(100, self.max_value):
            raise Exception("User entered an incorrect loot box value")
        return True

    def build_input(self):
        return discord.ui.TextInput(
            label="Enter a value up to {}".format(min(100, self.max_value)),
            style=discord.TextStyle.short,
            max_length=100,
            min_length=0,
            required=True
        )
