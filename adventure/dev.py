# -*- coding: utf-8 -*-
import asyncio
import logging
import random
from string import ascii_letters, digits
from typing import Optional, Union

import discord
from redbot.core import commands, bot
from redbot.core.i18n import Translator
from redbot.core.utils.chat_formatting import bold, box, humanize_number, pagify

from .abc import AdventureMixin
from .bank import bank
from .cart import Trader
from .charsheet import Character
from .constants import DEV_LIST
from .helpers import escape, is_dev
from .menus import BaseMenu, SimpleSource

_ = Translator("Adventure", __file__)

log = logging.getLogger("red.cogs.adventure")


class DevCommands(AdventureMixin):
    """This class will handle dealing with developer only commands"""

    async def no_dev_prompt(self, ctx: commands.Context) -> bool:
        if ctx.author.id in DEV_LIST:
            return True
        confirm_token = "".join(random.choices((*ascii_letters, *digits), k=16))
        await ctx.send(
            "**__You should not be running this command.__** "
            "Any issues that arise from you running this command will not be supported. "
            "If you wish to continue, enter this token as your next message."
            f"\n\n{confirm_token}"
        )
        try:
            message = await ctx.bot.wait_for(
                "message",
                check=lambda m: m.channel.id == ctx.channel.id and m.author.id == ctx.author.id,
                timeout=60,
            )
        except asyncio.TimeoutError:
            await ctx.send(_("Did not get confirmation, cancelling."))
            return False
        else:
            if message.content.strip() == confirm_token:
                return True
            else:
                await ctx.send(_("Did not get a matching confirmation, cancelling."))
                return False

    @commands.command(name="devcooldown")
    @commands.bot_has_permissions(add_reactions=True)
    @commands.is_owner()
    async def _devcooldown(self, ctx: commands.Context):
        """[Dev] Resets the after-adventure cooldown in this server."""
        if not await self.no_dev_prompt(ctx):
            return
        await self.config.guild(ctx.guild).cooldown.set(0)
        await ctx.tick()

    @commands.command()
    @commands.bot_has_permissions(add_reactions=True)
    @commands.is_owner()
    async def makecart(self, ctx: commands.Context, stockcount: Optional[int] = None):
        """[Dev] Force a cart to appear."""
        if not await self.no_dev_prompt(ctx):
            return
        trader = Trader(60, ctx, self)
        await trader.start(ctx, bypass=True, stockcount=stockcount)
        await asyncio.sleep(60)
        trader.stop()
        await trader.on_timeout()

    @commands.command()
    @commands.bot_has_permissions(add_reactions=True)
    @commands.is_owner()
    async def copyuser(self, ctx: commands.Context, user_id: int):
        """[Owner] Copy another members data to yourself.

        Note this overrides your current data.
        """
        user_data = await self.config.user_from_id(user_id).all()
        await self.config.user(ctx.author).set(user_data)
        await ctx.tick()

    @commands.command()
    @commands.bot_has_permissions(add_reactions=True)
    @commands.is_owner()
    async def devrebirth(
        self,
        ctx: commands.Context,
        rebirth_level: int = 1,
        character_level: int = 1,
        users: commands.Greedy[discord.Member] = None,
    ):
        """[Dev] Set multiple users rebirths and level."""
        if not await self.no_dev_prompt(ctx):
            return
        targets = users or [ctx.author]
        if not is_dev(ctx.author):
            if rebirth_level > 100:
                await ctx.send("Rebirth is too high.")
                await ctx.send_help()
                return
            elif character_level > 1000:
                await ctx.send("Level is too high.")
                await ctx.send_help()
                return
        for target in targets:
            async with self.get_lock(target):
                try:
                    c = await Character.from_json(ctx, self.config, target, self._daily_bonus)
                except Exception as exc:
                    log.exception("Error with the new character sheet", exc_info=exc)
                    continue
                bal = await bank.get_balance(target)
                if bal >= 1000:
                    withdraw = bal - 1000
                    await bank.withdraw_credits(target, withdraw)
                else:
                    withdraw = bal
                    await bank.set_balance(target, 0)
                character_data = await c.rebirth(dev_val=rebirth_level)
                await self.config.user(target).set(character_data)
                await ctx.send(
                    content=box(
                        _("{c}, congratulations on your rebirth.\nYou paid {bal}.").format(
                            c=escape(target.display_name), bal=humanize_number(withdraw)
                        ),
                        lang="ansi",
                    )
                )
            await self._add_rewards(ctx, target, int((character_level) ** 3.5) + 1, 0, False)
        await ctx.tick()

    @commands.command()
    @commands.bot_has_permissions(add_reactions=True)
    @commands.is_owner()
    async def devreset(self, ctx: commands.Context, users: commands.Greedy[Union[discord.Member, discord.User]]):
        """[Dev] Reset the skill cooldown for multiple users."""
        if not await self.no_dev_prompt(ctx):
            return
        targets = users or [ctx.author]
        for target in targets:
            async with self.get_lock(target):
                try:
                    c = await Character.from_json(ctx, self.config, target, self._daily_bonus)
                except Exception as exc:
                    log.exception("Error with the new character sheet", exc_info=exc)
                    continue
                c.heroclass["ability"] = False
                c.heroclass["cooldown"] = 0
                await self.config.user(target).set(await c.to_json(ctx, self.config))
        await ctx.tick()

    @commands.command(name="adventurestats")
    @commands.bot_has_permissions(add_reactions=True, embed_links=True)
    @commands.is_owner()
    async def _adventurestats(self, ctx: commands.Context):
        """[Owner] Show all current adventures."""
        msg = bold(_("Active Adventures\n"))
        embed_list = []

        if len(self._sessions) > 0:
            for server_id, adventure in self._sessions.items():
                stat_range = self._adv_results.get_stat_range(ctx)
                pdef = adventure.monster_modified_stats["pdef"]
                mdef = adventure.monster_modified_stats["mdef"]
                cdef = adventure.monster_modified_stats.get("cdef", 1.0)
                hp = int(
                    adventure.monster_modified_stats["hp"]
                    * self.ATTRIBS[adventure.attribute][0]
                    * adventure.monster_stats
                )
                dipl = int(
                    adventure.monster_modified_stats["dipl"]
                    * self.ATTRIBS[adventure.attribute][1]
                    * adventure.monster_stats
                )
                msg += (
                    f"{self.bot.get_guild(server_id).name} - "
                    f"[{adventure.challenge}]({adventure.message.jump_url})\n"
                    f"[{stat_range['stat_type']}-min:{stat_range['min_stat']}-max:{stat_range['max_stat']}-winratio:{stat_range['win_percent']}] "
                    f"(hp:{hp}-char:{dipl}-pdef:{pdef}-mdef:{mdef}-cdef:{cdef})\n\n"
                )
        else:
            msg += "None."
        for page in pagify(msg, delims=["\n\n"], page_length=1000):
            embed = discord.Embed(description=page)
            embed_list.append(embed)
        await BaseMenu(
            source=SimpleSource(embed_list),
            delete_message_after=True,
            clear_reactions_after=True,
            timeout=60,
        ).start(ctx=ctx)

    @commands.command(name="addtoauto", aliases=["a2a"])
    @commands.is_owner()
    async def _add_to_auto(self, ctx: commands.Context, *, players: str = None):
        """Add players to the auto list for the adventure in progress.
        `players` is a list of comma separated player IDs.
        """
        player_ids = [p.strip() for p in players.split(",")]
        members = [await self.bot.get_or_fetch_member(ctx.guild, player) for player in player_ids]
        session = self._sessions.get(ctx.guild.id, None)
        if session:
            session_lists = session.fight + session.magic + session.talk + session.pray + session.auto
            for player in members:
                if player in session_lists:
                    await ctx.send(box("{} ({}) is already part of the adventure.").format(player.display_name, str(player.id)))
                else:
                    await ctx.send(box("Adding {} ({}) to auto.").format(player.display_name, str(player.id)))
                    session.auto.append(player)
                await session.update()
        else:
            await ctx.send(box("There's no adventure right now."))

    @commands.command(name="listauto")
    @commands.is_owner()
    async def _listauto(self, ctx: commands.Context):
        """Get a list of users currently in the adventure (or previously on adventure if nothing in progress).
        """
        session = self._sessions.get(ctx.guild.id, None)
        if session:
            session_list = session.fight + session.magic + session.talk + session.pray + session.auto
        else:
            session_list = self._adv_results.get_last_auto_users(ctx)
        ids = [str(player.id) for player in session_list]
        await ctx.send(box("{}").format(",".join(ids)))
