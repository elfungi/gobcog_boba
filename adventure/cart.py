# -*- coding: utf-8 -*-
from __future__ import annotations

import logging
import random
import time
import math
from datetime import datetime, timedelta, timezone
from typing import Optional

import discord
from redbot.core import commands
from redbot.core.i18n import Translator
from redbot.core.utils.chat_formatting import box, humanize_number

from .bank import bank
from .charsheet import Character, Item
from .constants import ANSITextColours, Rarities, Slot
from .helpers import escape, is_dev, smart_embed, _sell_base

_ = Translator("Adventure", __file__)

log = logging.getLogger("red.cogs.adventure")


class TraderModal(discord.ui.Modal):
    def __init__(self, item: Item, cog: commands.Cog, view: Trader, ctx: commands.Context):
        super().__init__(title=_("How many would you like to buy?"))
        self.item = item
        self.cog = cog
        self.ctx = ctx
        self.view = view
        self.amount_input = discord.ui.TextInput(
            label=item.name[:43] + "..." if len(item.name) > 45 else item.name,  # discord form input allows 45 max len
            style=discord.TextStyle.short,
            placeholder=_("Amount"),
            max_length=100,
            min_length=0,
            required=False,
        )
        self.add_item(self.amount_input)

    async def wasting_time(self, interaction: discord.Interaction):
        await smart_embed(None, _("You're wasting my time."), interaction=interaction, ephemeral=True)

    async def only_one(self, interaction: discord.Interaction):
        await smart_embed(None, _("There's a limit of 1 per customer on this item!"), interaction=interaction, ephemeral=True)

    async def on_submit(self, interaction: discord.Interaction):
        if datetime.now(timezone.utc) >= self.view.end_time:
            self.view.stop()
            await interaction.response.send_message(
                _("{cart_name} has moved onto the next village.").format(cart_name=self.view.cart_name), ephemeral=True
            )
            return
        spender = interaction.user
        number = self.amount_input.value

        if not number:
            await self.wasting_time(interaction)
            return
        try:
            number = int(number)
        except ValueError:
            await self.wasting_time(interaction)
            return
        if number < 0:
            await self.wasting_time(interaction)
            return
        if number > 1 and self.item.rarity == Rarities.set or spender in self.view.restricted_users[self.item.name]:
            await self.only_one(interaction)
            return

        currency_name = await bank.get_currency_name(
            interaction.guild,
        )
        if currency_name.startswith("<"):
            currency_name = "credits"

        item = self.view.items.get(self.item.name, {})
        price = item.get("price") * number
        if await bank.can_spend(spender, price):
            await bank.withdraw_credits(spender, price)
            async with self.cog.get_lock(spender):
                try:
                    c = await Character.from_json(self.ctx, self.cog.config, spender, self.cog._daily_bonus)
                except Exception as exc:
                    log.exception("Error with the new character sheet", exc_info=exc)
                    return

                if c.is_backpack_full(is_dev=is_dev(spender)):
                    await interaction.response.send_message(
                        _("**{author}**, Your backpack is currently full.").format(author=escape(spender.display_name))
                    )
                    return
                item = self.item
                item.owned = number
                if item.rarity == Rarities.set:
                    self.view.restricted_users[item.name].append(spender)
                await c.add_to_backpack(item, number=number)
                await self.cog.config.user(spender).set(await c.to_json(self.ctx, self.cog.config))
                await interaction.response.send_message(
                    box(
                        _(
                            "{author} bought {p_result} {item_name} for "
                            "{item_price} {currency_name} and put it into their backpack."
                        ).format(
                            author=escape(spender.display_name),
                            p_result=number,
                            item_name=item.ansi,
                            item_price=humanize_number(price),
                            currency_name=currency_name,
                        ),
                        lang="ansi",
                    )
                )
        else:
            await interaction.response.send_message(
                _("**{author}**, you do not have enough {currency_name}.").format(
                    author=escape(spender.display_name), currency_name=currency_name
                )
            )


class TraderButton(discord.ui.Button):
    def __init__(self, item: Item, cog: commands.Cog):
        super().__init__(label=item.name)
        self.item = item
        self.cog = cog

    async def callback(self, interaction: discord.Interaction):
        if datetime.now(timezone.utc) >= self.view.end_time:
            self.view.stop()
            await self.view.on_timeout()
            await interaction.response.send_message(
                _("{cart_name} has moved onto the next village.").format(cart_name=self.view.cart_name), ephemeral=True
            )
            return
        modal = TraderModal(self.item, self.cog, view=self.view, ctx=self.view.ctx)
        await interaction.response.send_modal(modal)


class Trader(discord.ui.View):
    def __init__(self, timeout: float, ctx: commands.Context, cog: commands.Cog):
        super().__init__(timeout=timeout)
        self.cog = cog
        self.ctx = ctx
        self.items = {}
        self.message = None
        self.stock_str = ""
        self.end_time = datetime.now(timezone.utc) + timedelta(seconds=timeout)
        self.cart_name = _("Hawl's brother")
        self.restricted_users = {}

    async def on_timeout(self):
        if self.message is not None:
            timestamp = f"<t:{int(self.end_time.timestamp())}:R>"
            new_content = self.stock_str + _("{cart_name} left {time}.").format(
                time=timestamp, cart_name=self.cart_name
            )
            await self.message.edit(content=new_content, view=None)

    async def edit_timestamp(self):
        if self.timeout is None:
            return
        self.end_time = datetime.now(timezone.utc) + timedelta(seconds=self.timeout)
        timestamp = f"<t:{int(self.end_time.timestamp())}:R>"
        text = self.stock_str
        text += _("I am leaving {time}.\nDo you want to buy any of these fine items? Tell me which one below:").format(
            time=timestamp
        )
        await self.message.edit(content=text)

    async def start(self, ctx: commands.Context, bypass: bool = False, stockcount: Optional[int] = None):
        cart = await self.cog.config.cart_name()
        if await self.cog.config.guild(ctx.guild).cart_name():
            cart = await self.cog.config.guild(ctx.guild).cart_name()
        self.cart_name = cart
        cart_header = _("[{cart_name} is bringing the cart around!]").format(cart_name=cart)
        text = box(ANSITextColours.blue.as_str(cart_header), lang="ansi")
        if ctx.guild.id not in self.cog._last_trade:
            self.cog._last_trade[ctx.guild.id] = 0

        if not bypass:
            if self.cog._last_trade[ctx.guild.id] == 0:
                self.cog._last_trade[ctx.guild.id] = time.time()
            elif self.cog._last_trade[ctx.guild.id] >= time.time() - self.timeout:
                # trader can return after 3 hours have passed since last visit.
                return  # silent return.
        self.cog._last_trade[ctx.guild.id] = time.time()

        room = await self.cog.config.guild(ctx.guild).cartroom()
        if room:
            room = ctx.guild.get_channel(room)
        if room is None or bypass:
            room = ctx
        self.cog.bot.dispatch("adventure_cart", ctx)  # dispatch after silent return
        if stockcount is None:
            stockcount = 10
        self.cog._curent_trader_stock[ctx.guild.id] = (stockcount, {})

        stock = await self.generate(stockcount)
        currency_name = await bank.get_currency_name(
            ctx.guild,
        )
        if str(currency_name).startswith("<"):
            currency_name = "credits"
        for (index, item) in enumerate(stock):
            item = stock[index]
            self.restricted_users[item["item"].name] = []
            if item["item"].slot is Slot.two_handed:  # two handed weapons add their bonuses twice
                hand = item["item"].slot.get_name()
                att = item["item"].att * 2
                cha = item["item"].cha * 2
                intel = item["item"].int * 2
                luck = item["item"].luck * 2
                dex = item["item"].dex * 2
            else:
                if item["item"].slot is Slot.right or item["item"].slot is Slot.left:
                    hand = item["item"].slot.get_name() + _(" handed")
                else:
                    hand = item["item"].slot.get_name() + _(" slot")
                att = item["item"].att
                cha = item["item"].cha
                intel = item["item"].int
                luck = item["item"].luck
                dex = item["item"].dex
            text += box(
                _(
                    "\n{item_name} [{hand}] ("
                    "Lv: {lvl}, "
                    "ATT: {str_att}, "
                    "CHA: {str_cha}, "
                    "INT: {str_int}, "
                    "DEX: {str_dex}, "
                    "LUK: {str_luck} "
                    ") {item_price} {currency_name}."
                ).format(
                    item_name=item["item"].ansi,
                    lvl=item["item"].lvl,
                    str_att=str(att),
                    str_int=str(intel),
                    str_cha=str(cha),
                    str_luck=str(luck),
                    str_dex=str(dex),
                    hand=hand,
                    item_price=humanize_number(item["price"]),
                    currency_name=currency_name,
                ),
                lang="ansi",
            )
        self.stock_str = text
        timestamp = f"<t:{int(self.end_time.timestamp())}:R>"
        text += _("I am leaving {time}.\nDo you want to buy any of these fine items? Tell me which one below:").format(
            time=timestamp
        )
        self.message = await room.send(text, view=self)

    async def generate(self, howmany: int = 10):
        output = {}
        howmany = max(min(25, howmany), 1)
        while len(self.items) < howmany:
            rarity_roll = random.random()
            is_set_item = False

            # 5% set
            if rarity_roll >= 0.95:
                item = await self.ctx.cog._genitem(self.ctx, Rarities.set)
                is_set_item = True
            # 10% ascended
            elif rarity_roll >= 0.85:
                item = await self.ctx.cog._genitem(self.ctx, Rarities.ascended)
            # 20% legendary
            elif rarity_roll >= 0.65:
                item = await self.ctx.cog._genitem(self.ctx, Rarities.legendary)
            # 30% epic
            elif rarity_roll >= 0.35:
                item = await self.ctx.cog._genitem(self.ctx, Rarities.epic)
            # 25% rare
            elif rarity_roll >= 0.10:
                item = await self.ctx.cog._genitem(self.ctx, Rarities.rare)
            # 10% normal
            else:
                item = await self.ctx.cog._genitem(self.ctx, Rarities.normal)

            base, price_func = _sell_base(item)
            if is_set_item:
                # set items have a low base sell price so mark them up significantly
                # however, stats on these set piece vary wildly, so we use a log function to normalize out the values
                # targeting a price range of 750k-1.2m
                normalized_stats = math.log(item.max_main_stat, 3) + 10
                price = round(max(price_func(normalized_stats), base) * 1300)
            else:
                # want 80% sell price buying price - mark up 1.25
                price = round(max(price_func(item.max_main_stat), base) * 1.6)

            self.items.update({item.name: {"itemname": item.name, "item": item, "price": price, "lvl": item.lvl}})
            self.add_item(TraderButton(item, self.cog))

        for (index, item) in enumerate(self.items):
            output.update({index: self.items[item]})
        return output
