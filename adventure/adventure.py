# -*- coding: utf-8 -*-
import asyncio
import contextlib
import json
import logging
import random
import time
from abc import ABC
from datetime import datetime, timedelta
from types import SimpleNamespace
from typing import Dict, Literal, MutableMapping, Optional, Tuple, Union

import discord
from discord.ext.commands import CheckFailure
from redbot import VersionInfo, version_info
from redbot.core import Config, commands
from redbot.core.bot import Red
from redbot.core.data_manager import bundled_data_path, cog_data_path
from redbot.core.errors import BalanceTooHigh
from redbot.core.i18n import Translator, cog_i18n
from redbot.core.utils import AsyncIter
from redbot.core.utils.chat_formatting import bold, box, humanize_list, humanize_number, pagify
from redbot.core.utils.predicates import ReactionPredicate

from .adventureresult import AdventureResults
from .adventureset import AdventureSetCommands
from .backpack import BackPackCommands
from .bank import bank
from .cart import Trader
from .character import CharacterCommands
from .charsheet import Character, Item, calculate_sp, has_funds
from .class_abilities import ClassAbilities
from .constants import DEV_LIST, ANSITextColours, HeroClasses, Rarities, Treasure, HC_VETERAN_RANK
from .converters import ArgParserFailure, ChallengeConverter
from .defaults import default_global, default_guild, default_user
from .dev import DevCommands
from .economy import EconomyCommands
from .game_session import GameSession
from .helpers import _get_epoch, _remaining, is_dev, smart_embed
from .leaderboards import LeaderboardCommands
from .loadouts import LoadoutCommands
from .loot import LootCommands
from .negaverse import Negaverse
from .rebirth import RebirthCommands
from .themeset import ThemesetCommands
from .types import Monster

_ = Translator("Adventure", __file__)

log = logging.getLogger("red.cogs.adventure")


_SCHEMA_VERSION = 4
_config: Config = None


class CompositeMetaClass(type(commands.Cog), type(ABC)):
    """
    This allows the metaclass used for proper type detection to
    coexist with discord.py's metaclass
    """

    pass


@cog_i18n(_)
class Adventure(
    AdventureSetCommands,
    BackPackCommands,
    CharacterCommands,
    ClassAbilities,
    DevCommands,
    EconomyCommands,
    LeaderboardCommands,
    LoadoutCommands,
    LootCommands,
    Negaverse,
    RebirthCommands,
    ThemesetCommands,
    commands.GroupCog,
    metaclass=CompositeMetaClass,
):
    """Adventure, derived from the Goblins Adventure cog by locastan."""

    async def red_delete_data_for_user(
        self,
        *,
        requester: Literal["discord", "owner", "user", "user_strict"],
        user_id: int,
    ):
        await self.config.user_from_id(user_id).clear()
        await bank._config.user_from_id(
            user_id
        ).clear()  # This will only ever touch the separate currency, leaving bot economy to be handled by core.

    __version__ = "4.7.8"

    def __init__(self, bot: Red):
        self.bot = bot
        bank._init(bot)
        self._last_trade = {}
        self._adv_results = AdventureResults(10)
        self.emojis = SimpleNamespace()
        self.emojis.fumble = "\N{EXCLAMATION QUESTION MARK}\N{VARIATION SELECTOR-16}"
        self.emojis.level_up = "\N{BLACK UP-POINTING DOUBLE TRIANGLE}"
        self.emojis.rebirth = "\N{BABY SYMBOL}"
        self.emojis.attack = "\N{DAGGER KNIFE}\N{VARIATION SELECTOR-16}"
        self.emojis.magic = "\N{SPARKLES}"
        self.emojis.talk = "\N{LEFT SPEECH BUBBLE}\N{VARIATION SELECTOR-16}"
        self.emojis.pray = "\N{PERSON WITH FOLDED HANDS}"
        self.emojis.run = "\N{RUNNER}\N{ZERO WIDTH JOINER}\N{MALE SIGN}\N{VARIATION SELECTOR-16}"
        self.emojis.crit = "\N{COLLISION SYMBOL}"
        self.emojis.magic_crit = "\N{HIGH VOLTAGE SIGN}"
        self.emojis.berserk = "\N{RIGHT ANGER BUBBLE}\N{VARIATION SELECTOR-16}"
        self.emojis.dice = "\N{GAME DIE}"
        self.emojis.yes = "\N{WHITE HEAVY CHECK MARK}"
        self.emojis.no = "\N{NEGATIVE SQUARED CROSS MARK}"
        self.emojis.sell = "\N{MONEY BAG}"
        self.emojis.skills = SimpleNamespace()
        self.emojis.skills.bless = "\N{SCROLL}"
        self.emojis.skills.psychic = "\N{SIX POINTED STAR WITH MIDDLE DOT}"
        self.emojis.skills.berserker = self.emojis.berserk
        self.emojis.skills.wizzard = self.emojis.magic_crit
        self.emojis.skills.bard = "\N{EIGHTH NOTE}\N{BEAMED EIGHTH NOTES}\N{BEAMED SIXTEENTH NOTES}"
        self.emojis.hp = "\N{HEAVY BLACK HEART}\N{VARIATION SELECTOR-16}"
        self.emojis.auto = "\N{CLOCKWISE RIGHTWARDS AND LEFTWARDS OPEN CIRCLE ARROWS}"
        self.emojis.dipl = self.emojis.talk
        self.red_340_or_newer = version_info >= VersionInfo.from_str("3.4.0")

        self._adventure_actions = [
            self.emojis.attack,
            self.emojis.magic,
            self.emojis.talk,
            self.emojis.pray,
            self.emojis.run,
        ]
        self._adventure_controls = {
            "fight": self.emojis.attack,
            "magic": self.emojis.magic,
            "talk": self.emojis.talk,
            "pray": self.emojis.pray,
            "run": self.emojis.run,
        }
        self._treasure_controls = {
            self.emojis.yes: "equip",
            self.emojis.no: "backpack",
            self.emojis.sell: "sell",
        }
        self._yes_no_controls = {self.emojis.yes: "yes", self.emojis.no: "no"}

        self._adventure_countdown = {}
        self._rewards = {}
        self._reward_message = {}
        self._loss_message = {}
        self._trader_countdown = {}
        self._current_traders = {}
        self._curent_trader_stock = {}
        self._sessions: MutableMapping[int, GameSession] = {}
        self._session_waits: MutableMapping[int: bool] = {}
        self._react_messaged = []
        self.tasks = {}
        self.locks: MutableMapping[int, asyncio.Lock] = {}
        self.gb_task = None

        self.config = Config.get_conf(self, 2_710_801_001, force_registration=True)
        self._daily_bonus = {}
        self._separate_economy = None

        self.RAISINS: list = None
        self.THREATEE: list = None
        self.TR_GEAR_SET: dict = None
        self.ATTRIBS: dict = None
        self.MONSTERS: dict = None
        self.AS_MONSTERS: dict = None
        self.MONSTER_NOW: dict = None
        self.LOCATIONS: list = None
        self.PETS: dict = None
        self.ACTION_RESPONSE: dict = None

        self.config.register_guild(**default_guild)
        self.config.register_global(**default_global)
        self.config.register_user(**default_user)
        self.cleanup_loop = self.bot.loop.create_task(self.cleanup_tasks())
        log.debug("Creating Task")
        self._init_task = self.bot.loop.create_task(self.initialize())
        self._ready_event = asyncio.Event()
        # This is done to prevent having a top level text command named "start"
        # in order to keep the slash command variant called `/adventure start`
        # which is a lot better than `/adventure adventure`
        self.app_command.remove_command("adventure")
        self._adventure.app_command.name = "start"
        self.app_command.add_command(self._adventure.app_command)
        self._commit = ""
        self._repo = ""

    def format_help_for_context(self, ctx: commands.Context) -> str:
        """
        Thanks Sinbad!

        How many people are going to copy this one?
        """
        pre_processed = super().format_help_for_context(ctx)
        ret = f"{pre_processed}\n\nCog Version: {self.__version__}\n"
        # we'll only have a repo if the cog was installed through Downloader at some point
        if self._repo:
            ret += f"Repo: {self._repo}\n"
            ret += f"Commit: [{self._commit[:9]}]({self._repo}/tree/{self._commit})"
        else:
            ret += "Repo: Unknown Repo\n"
            if self._commit:
                ret += f"Commit: {self._commit}"
            else:
                ret += "Commit: Unknown commit"
        return ret

    async def cog_before_invoke(self, ctx: commands.Context):
        await self._ready_event.wait()
        if ctx.author.id in self.locks and self.locks[ctx.author.id].locked():
            await ctx.send(_("You're already interacting with something that needs your attention!"), ephemeral=True)
            raise CheckFailure(f"There's an active lock for this user ({ctx.author.id})")
        return True

    async def _clear_react(self, msg: discord.Message):
        with contextlib.suppress(discord.HTTPException):
            await msg.clear_reactions()

    async def initialize(self):
        """This will load all the bundled data into respective variables."""
        await self.bot.wait_until_red_ready()
        downloader = self.bot.get_cog("Downloader")
        if downloader is not None:
            cogs = await downloader.installed_cogs()
            for cog in cogs:
                if cog.name == "adventure":
                    if cog.repo is not None:
                        self._repo = cog.repo.clean_url
                    self._commit = cog.commit
        try:
            global _config
            _config = self.config
            theme = await self.config.theme()
            self._separate_economy = await self.config.separate_economy()
            if theme in {"default"}:
                get_path = bundled_data_path
            else:
                get_path = cog_data_path

            as_monster_fp = get_path(self) / f"{theme}" / "as_monsters.json"
            attribs_fp = get_path(self) / f"{theme}" / "attribs.json"
            locations_fp = get_path(self) / f"{theme}" / "locations.json"
            monster_fp = get_path(self) / f"{theme}" / "monsters.json"
            pets_fp = get_path(self) / f"{theme}" / "pets.json"
            raisins_fp = get_path(self) / f"{theme}" / "raisins.json"
            threatee_fp = get_path(self) / f"{theme}" / "threatee.json"
            tr_set_fp = get_path(self) / f"{theme}" / "tr_set.json"
            prefixes_fp = get_path(self) / f"{theme}" / "prefixes.json"
            materials_fp = get_path(self) / f"{theme}" / "materials.json"
            equipment_fp = get_path(self) / f"{theme}" / "equipment.json"
            suffixes_fp = get_path(self) / f"{theme}" / "suffixes.json"
            set_bonuses = get_path(self) / f"{theme}" / "set_bonuses.json"
            set_upgrades = get_path(self) / f"{theme}" / "set_bonuses_upgrades.json"
            action_response = get_path(self) / f"{theme}" / "action_response.json"
            files = {
                "pets": pets_fp,
                "attr": attribs_fp,
                "monster": monster_fp,
                "location": locations_fp,
                "raisins": raisins_fp,
                "threatee": threatee_fp,
                "set": tr_set_fp,
                "as_monsters": as_monster_fp,
                "prefixes": prefixes_fp,
                "materials": materials_fp,
                "equipment": equipment_fp,
                "suffixes": suffixes_fp,
                "set_bonuses": set_bonuses,
                "set_upgrades": set_upgrades,
                "action_response": action_response,
            }
            for name, file in files.items():
                if not file.exists():
                    files[name] = bundled_data_path(self) / "default" / f"{file.name}"

            with files["pets"].open("r") as f:
                self.PETS = json.load(f)
            with files["attr"].open("r") as f:
                self.ATTRIBS = json.load(f)
            with files["monster"].open("r") as f:
                self.MONSTERS = json.load(f)
            with files["as_monsters"].open("r") as f:
                self.AS_MONSTERS = json.load(f)
            with files["location"].open("r") as f:
                self.LOCATIONS = json.load(f)
            with files["raisins"].open("r") as f:
                self.RAISINS = json.load(f)
            with files["threatee"].open("r") as f:
                self.THREATEE = json.load(f)
            with files["set"].open("r") as f:
                self.TR_GEAR_SET = json.load(f)
            with files["prefixes"].open("r") as f:
                self.PREFIXES = json.load(f)
            with files["materials"].open("r") as f:
                self.MATERIALS = json.load(f)
            with files["equipment"].open("r") as f:
                self.EQUIPMENT = json.load(f)
            with files["suffixes"].open("r") as f:
                self.SUFFIXES = json.load(f)
            with files["set_bonuses"].open("r") as f:
                self.SET_BONUSES = json.load(f)
            with files["set_upgrades"].open("r") as f:
                self.SET_UPGRADES = json.load(f)
            with files["action_response"].open("r") as f:
                self.ACTION_RESPONSE = json.load(f)

            if not all(
                i
                for i in [
                    len(self.PETS) > 0,
                    len(self.ATTRIBS) > 0,
                    len(self.MONSTERS) > 0,
                    len(self.LOCATIONS) > 0,
                    len(self.RAISINS) > 0,
                    len(self.THREATEE) > 0,
                    len(self.TR_GEAR_SET) > 0,
                    len(self.PREFIXES) > 0,
                    len(self.MATERIALS) > 0,
                    len(self.EQUIPMENT) > 0,
                    len(self.SUFFIXES) > 0,
                    len(self.SET_BONUSES) > 0,
                    len(self.SET_UPGRADES) > 0
                ]
            ):
                log.critical(f"{theme} theme is invalid, resetting it to the default theme.")
                await self.config.theme.set("default")
                await self.initialize()
                return
            await self._migrate_config(from_version=await self.config.schema_version(), to_version=_SCHEMA_VERSION)
            self._daily_bonus = await self.config.daily_bonus.all()
        except Exception as err:
            log.exception("There was an error starting up the cog", exc_info=err)
        else:
            self._ready_event.set()
            self.gb_task = self.bot.loop.create_task(self._garbage_collection())

    async def cleanup_tasks(self):
        await self._ready_event.wait()
        while self is self.bot.get_cog("Adventure"):
            to_delete = []
            for msg_id, task in self.tasks.items():
                if task.done():
                    to_delete.append(msg_id)
            for task in to_delete:
                del self.tasks[task]
            await asyncio.sleep(300)

    async def _migrate_config(self, from_version: int, to_version: int) -> None:
        log.debug(f"from_version: {from_version} to_version:{to_version}")
        if from_version == to_version:
            return
        if from_version < 2 <= to_version:
            group = self.config._get_base_group(self.config.USER)
            accounts = await group.all()
            tmp = accounts.copy()
            async with group.all() as adventurers_data:
                for user in tmp:
                    new_backpack = {}
                    new_loadout = {}
                    user_equipped_items = adventurers_data[user]["items"]
                    for slot in user_equipped_items.keys():
                        if user_equipped_items[slot]:
                            for slot_item_name, slot_item in list(user_equipped_items[slot].items())[:1]:
                                new_name, slot_item = self._convert_item_migration(slot_item_name, slot_item)
                                adventurers_data[user]["items"][slot] = {new_name: slot_item}
                    if "backpack" not in adventurers_data[user]:
                        adventurers_data[user]["backpack"] = {}
                    for backpack_item_name, backpack_item in adventurers_data[user]["backpack"].items():
                        new_name, backpack_item = self._convert_item_migration(backpack_item_name, backpack_item)
                        new_backpack[new_name] = backpack_item
                    adventurers_data[user]["backpack"] = new_backpack
                    if "loadouts" not in adventurers_data[user]:
                        adventurers_data[user]["loadouts"] = {}
                    try:
                        for loadout_name, loadout in adventurers_data[user]["loadouts"].items():
                            for slot, equipped_loadout in loadout.items():
                                new_loadout[slot] = {}
                                for loadout_item_name, loadout_item in equipped_loadout.items():
                                    new_name, loadout_item = self._convert_item_migration(
                                        loadout_item_name, loadout_item
                                    )
                                    new_loadout[slot][new_name] = loadout_item
                        adventurers_data[user]["loadouts"] = new_loadout
                    except Exception:
                        adventurers_data[user]["loadouts"] = {}
            await self.config.schema_version.set(2)
            from_version = 2
        if from_version < 3 <= to_version:
            group = self.config._get_base_group(self.config.USER)
            accounts = await group.all()
            tmp = accounts.copy()
            async with group.all() as adventurers_data:
                for user in tmp:
                    new_loadout = {}
                    if "loadouts" not in adventurers_data[user]:
                        adventurers_data[user]["loadouts"] = {}
                    try:
                        for loadout_name, loadout in adventurers_data[user]["loadouts"].items():
                            if loadout_name in {
                                "head",
                                "neck",
                                "chest",
                                "gloves",
                                "belt",
                                "legs",
                                "boots",
                                "left",
                                "right",
                                "ring",
                                "charm",
                            }:
                                continue
                            new_loadout[loadout_name] = loadout
                        adventurers_data[user]["loadouts"] = new_loadout
                    except Exception:
                        adventurers_data[user]["loadouts"] = {}
            await self.config.schema_version.set(3)

        if from_version < 4 <= to_version:
            group = self.config._get_base_group(self.config.USER)
            accounts = await group.all()
            tmp = accounts.copy()
            async with group.all() as adventurers_data:
                async for user in AsyncIter(tmp, steps=100):
                    if "items" in tmp[user]:
                        equipped = tmp[user]["items"]
                        for slot, item in equipped.items():
                            for item_name, item_data in item.items():
                                if "King Solomos" in item_name:
                                    del adventurers_data[user]["items"][slot][item_name]
                                    item_name = item_name.replace("Solomos", "Solomons")
                                    adventurers_data[user]["items"][slot][item_name] = item_data
                    if "loadouts" in tmp[user]:
                        loadout = tmp[user]["loadouts"]
                        for loadout_name, loadout_data in loadout.items():
                            for slot, item in equipped.items():
                                for item_name, item_data in item.items():
                                    if "King Solomos" in item_name:
                                        del adventurers_data[user]["loadouts"][loadout_name][slot][item_name]
                                        item_name = item_name.replace("Solomos", "Solomons")
                                        adventurers_data[user]["loadouts"][loadout_name][slot][item_name] = item_data
                    if "backpack" in tmp[user]:
                        backpack = tmp[user]["backpack"]
                        async for item_name, item_data in AsyncIter(backpack.items(), steps=100):
                            if "King Solomos" in item_name:
                                del adventurers_data[user]["backpack"][item_name]
                                item_name = item_name.replace("Solomos", "Solomons")
                                adventurers_data[user]["backpack"][item_name] = item_data
            await self.config.schema_version.set(4)

    def _convert_item_migration(self, item_name, item_dict):
        new_name = item_name
        if "name" in item_dict:
            del item_dict["name"]
        if "rarity" not in item_dict:
            item_dict["rarity"] = "common"
        if item_dict["rarity"] == "legendary":
            new_name = item_name.replace("{Legendary:'", "").replace("legendary:'", "").replace("'}", "")
        if item_dict["rarity"] == "epic":
            new_name = item_name.replace("[", "").replace("]", "")
        if item_dict["rarity"] == "rare":
            new_name = item_name.replace("_", " ").replace(".", "")
        if item_dict["rarity"] == "set":
            new_name = (
                item_name.replace("{Gear_Set:'", "")
                .replace("{gear_set:'", "")
                .replace("{Gear Set:'", "")
                .replace("'}", "")
            )
        if item_dict["rarity"] != "set":
            if "bonus" in item_dict:
                del item_dict["bonus"]
            if "parts" in item_dict:
                del item_dict["parts"]
            if "set" in item_dict:
                del item_dict["set"]
        return (new_name, item_dict)

    def in_adventure(self, ctx: Optional[commands.Context] = None, user: Optional[discord.Member] = None) -> bool:
        """
        Returns `True` if the user is in an adventure or otherwise engaged
        with something requiring their attention.
        """
        author = user or ctx.author
        sessions = self._sessions
        if not sessions:
            return False or self.get_lock(author).locked()
        for session in self._sessions.values():
            if session.in_adventure(author):
                return True
        return False or self.get_lock(author).locked()

    async def allow_in_dm(self, ctx):
        """Checks if the bank is global and allows the command in dm."""
        if ctx.guild is not None:
            return True
        return bool(ctx.guild is None and await bank.is_global())

    def get_lock(self, member: discord.User) -> asyncio.Lock:
        if member.id not in self.locks:
            self.locks[member.id] = asyncio.Lock()
        return self.locks[member.id]

    async def _garbage_collection(self):
        await self.bot.wait_until_red_ready()
        delta = timedelta(minutes=6)
        with contextlib.suppress(asyncio.CancelledError):
            while True:
                async for guild_id, session in AsyncIter(self._sessions.copy().items(), steps=100):
                    if datetime.now() > (session.start_time + delta):
                        if guild_id in self._sessions:
                            log.debug("Removing old session from %s", guild_id)
                            del self._sessions[guild_id]
                await asyncio.sleep(5)

    @commands.cooldown(rate=1, per=5, type=commands.BucketType.guild)
    @commands.hybrid_command(name="adventure", aliases=["a"])
    @commands.bot_has_permissions(add_reactions=True)
    @commands.guild_only()
    async def _adventure(self, ctx: commands.Context, *, challenge: Optional[ChallengeConverter] = None):
        """This will send you on an adventure!

        You play by reacting with the offered emojis.
        """
        await ctx.defer()
        if ctx.guild.id and self._session_waits and self._session_waits[ctx.guild.id] is True:
            return await smart_embed(
                ctx,
                _(
                    f"The next adventure is already queued up! Check your supplies and get ready!"
                ),
            )
        if ctx.guild.id in self._sessions and self._sessions[ctx.guild.id].finished is False:
            adventure_obj = self._sessions[ctx.guild.id]
            link = adventure_obj.message.jump_url

            challenge = adventure_obj.challenge if (adventure_obj.easy_mode or adventure_obj.exposed) else _("Unknown")
            return await smart_embed(
                ctx,
                _(
                    f"There's already another adventure going on in this server.\n"
                    f"Currently fighting: [{challenge}]({link})"
                ),
            )

        if not await has_funds(ctx.author, 250):
            currency_name = await bank.get_currency_name(
                ctx.guild,
            )
            extra = (
                _("\nRun `{ctx.clean_prefix}apayday` to get some gold.").format(ctx=ctx)
                if self._separate_economy
                else ""
            )
            return await smart_embed(
                ctx,
                _("You need {req} {name} to start an adventure.{extra}").format(
                    req=250, name=currency_name, extra=extra
                ),
            )
        self._session_waits[ctx.guild.id] = True
        guild_settings = await self.config.guild(ctx.guild).all()
        cooldown = guild_settings["cooldown"]
        cooldown_time = guild_settings["cooldown_timer_manual"]

        if cooldown + cooldown_time > time.time() and ctx.author.id not in DEV_LIST:
            next_start_time = int(cooldown + cooldown_time + 3)  # add 3s buffer for processing time
            await smart_embed(
                ctx,
                _("Alright {}, the next adventure will start in about <t:{}:R>!").format(ctx.author.display_name, next_start_time),
            )
            await asyncio.sleep(int(cooldown_time))

        if challenge and not (is_dev(ctx.author) or await ctx.bot.is_owner(ctx.author)):
            # Only let the bot owner specify a specific challenge
            challenge = None

        adventure_msg = _("You feel adventurous, {}?").format(bold(ctx.author.display_name))
        try:
            self._session_waits[ctx.guild.id] = False
            reward, participants = await self._simple(ctx, adventure_msg, challenge)
            await self.config.guild(ctx.guild).cooldown.set(time.time())
            if ctx.guild.id in self._sessions:
                self._sessions[ctx.guild.id].finished = True
        except Exception as exc:
            if ctx.guild.id in self._sessions:
                self._sessions[ctx.guild.id].finished = True
            await self.config.guild(ctx.guild).cooldown.set(0)
            log.exception("Something went wrong controlling the game", exc_info=exc)
            while ctx.guild.id in self._sessions:
                del self._sessions[ctx.guild.id]
            return
        if not reward and not participants:
            await self.config.guild(ctx.guild).cooldown.set(0)
            while ctx.guild.id in self._sessions:
                del self._sessions[ctx.guild.id]
            return
        reward_copy = reward.copy()
        send_message = ""
        for userid, rewards in reward_copy.items():
            if rewards:
                user = ctx.guild.get_member(userid)  # bot.get_user breaks sometimes :ablobsweats:
                if user is None:
                    # sorry no rewards if you leave the server
                    continue
                msg = await self._add_rewards(ctx, user, rewards["xp"], rewards["cp"], rewards["special"])
                if msg:
                    send_message += f"{msg}\n"
                self._rewards[userid] = {}
        if send_message:
            for page in pagify(send_message):
                await smart_embed(ctx, page, success=True)
        if participants:
            for user in participants:  # reset activated abilities
                async with self.get_lock(user):
                    try:
                        c = await Character.from_json(ctx, self.config, user, self._daily_bonus)
                    except Exception as exc:
                        log.exception("Error with the new character sheet", exc_info=exc)
                        continue
                    if c.heroclass["ability"]:
                        c.heroclass["ability"] = False
                    if c.last_currency_check + 600 < time.time() or c.bal > c.last_known_currency:
                        c.last_known_currency = await bank.get_balance(user)
                        c.last_currency_check = time.time()
                    await self.config.user(user).set(await c.to_json(ctx, self.config))
        if ctx.message.id in self._reward_message:
            extramsg = self._reward_message.pop(ctx.message.id)
            if extramsg:
                for msg in pagify(extramsg, page_length=1900):
                    await smart_embed(ctx, msg, success=True)
        if ctx.message.id in self._loss_message:
            extramsg = self._loss_message.pop(ctx.message.id)
            if extramsg:
                extramsg = _(f"{extramsg} to repair their gear.")
                for msg in pagify(extramsg, page_length=1900):
                    await smart_embed(ctx, msg, success=False)
        while ctx.guild.id in self._sessions:
            del self._sessions[ctx.guild.id]

    @_adventure.error
    async def _error_handler(self, ctx: commands.Context, error: Exception) -> None:
        error = getattr(error, "original", error)
        handled = False
        if not isinstance(
            error,
            (
                commands.CheckFailure,
                commands.UserInputError,
                commands.DisabledCommand,
                commands.CommandOnCooldown,
            ),
        ):
            if ctx.guild.id in self._sessions:
                self._sessions[ctx.guild.id].finished = True
            while ctx.guild.id in self._sessions:
                del self._sessions[ctx.guild.id]
            handled = False
        elif isinstance(error, RuntimeError):
            handled = True

        await ctx.bot.on_command_error(ctx, error, unhandled_by_cog=not handled)

    async def cog_command_error(self, ctx: commands.Context, error: Exception) -> None:
        error = getattr(error, "original", error)
        handled = False
        if hasattr(ctx.command, "on_error"):
            return
        if isinstance(error, ArgParserFailure):
            handled = True
            msg = _("`{command}` {message}").format(
                message=error.message,
                command=error.cmd,
            )
            await ctx.send(msg)
        elif isinstance(error, discord.NotFound):
            handled = True
            msg = _("An important message has been deleted, please try again.").format(
                message=error.message,
                command=error.cmd,
            )
            await ctx.send(msg)
            lock = self.get_lock(ctx.author)  # This is a guess ... but its better than not handled.
            with contextlib.suppress(Exception):
                if lock.locked():
                    lock.release()

        await ctx.bot.on_command_error(ctx, error, unhandled_by_cog=not handled)

    async def get_challenge(self, ctx: commands.Context, monsters):
        return random.choice(list(monsters.keys()))

    @staticmethod
    def fluctuate_stats(value, bottom):
        return random.uniform(bottom, bottom + 0.4) * value

    def _dynamic_monster_stats_simple(self, ctx: commands.Context, choice: Monster, monster_stats) -> Monster:
        stat_range = self._adv_results.get_stat_range(ctx)
        average_attack = stat_range["average_attack"]
        average_talk = stat_range["average_talk"]
        win_percent = stat_range["win_percent"]

        if average_attack == 0:
            choice["hp"] = self.fluctuate_stats(choice["hp"] * monster_stats, win_percent)
        else:
            choice["hp"] = self.fluctuate_stats(average_attack * monster_stats, win_percent)
        if average_talk == 0:
            choice["dipl"] = self.fluctuate_stats(choice["dipl"] * monster_stats, win_percent)
        else:
            choice["dipl"] = self.fluctuate_stats(average_talk * monster_stats, win_percent)
        choice["pdef"] = self.fluctuate_stats(choice["pdef"], win_percent)
        choice["mdef"] = self.fluctuate_stats(choice["mdef"], win_percent)
        choice["cdef"] = self.fluctuate_stats(choice.get("cdef", 1.0), win_percent)
        return choice

    async def update_monster_roster(self) -> Tuple[Dict[str, Monster], float, bool]:
        """
        Gets the current list of available monsters, their stats, and whether
        or not to spawn a transcended.

        Returns
        -------
            Tuple[Dict[str, Monster], float, bool]
                The Available monsters dictionary, the stats they should have scaled,
                and whether or not it is transcended.
        """
        transcended_chance = random.randint(0, 10)
        normal_monsters_list = random.sample(list(self.MONSTERS.items()), 60)
        normal_monsters = {}
        for name, monster in normal_monsters_list:
            normal_monsters[name] = monster
        theme = await self.config.theme()
        extra_monsters = await self.config.themes.all()
        extra_monsters = extra_monsters.get(theme, {}).get("monsters", {})
        monsters = {**normal_monsters, **self.AS_MONSTERS, **extra_monsters}

        # shuffle the monsters to guarantee randomness, then prune the list so that only ~10% are bosses
        monster_names = list(monsters.keys())
        random.shuffle(monster_names)
        target_boss_percent = round(0.10 * len(monster_names))
        boss_count = 0
        result = {}
        for name in monster_names:
            monster = monsters[name]
            if monster["boss"]:
                if boss_count >= target_boss_percent:
                    continue
                boss_count += 1
            result[name] = monster
        # bosses = [m for _i, m in enumerate(result.values()) if m["boss"]]
        # print(len(result), len(bosses), (len(bosses) / len(result) * 100))
        transcended = False
        # set our default return values first
        monster_stats = 1.0

        if transcended_chance > 8:
            monster_stats = random.uniform(1, 1.3)
            transcended = True
        return result, monster_stats, transcended

    async def _simple(self, ctx: commands.Context, adventure_msg, challenge: str = None, attribute: str = None):
        self.bot.dispatch("adventure", ctx)
        text = ""
        c = await Character.from_json(ctx, self.config, ctx.author, self._daily_bonus)
        easy_mode = await self.config.easy_mode()
        if not easy_mode:
            if c.rebirths >= 30:
                easy_mode = False
            elif c.rebirths >= 20:
                easy_mode = bool(random.getrandbits(1))
            else:
                easy_mode = True

        monster_roster, monster_stats, transcended = await self.update_monster_roster()
        if not challenge or challenge not in monster_roster:
            challenge = await self.get_challenge(ctx, monster_roster)

        if attribute and attribute.lower() in self.ATTRIBS:
            attribute = attribute.lower()
        else:
            attribute = random.choice(list(self.ATTRIBS.keys()))
        new_challenge = challenge
        if easy_mode:
            if transcended:
                # Shows Transcended on Easy mode
                new_challenge = _("Transcended {}").format(challenge.replace("Ascended", ""))
            no_monster = False
            if monster_roster[challenge]["boss"]:
                timer = 60 * 5
                self.bot.dispatch("adventure_boss", ctx)
                challenge_str = _("[{challenge} Alarm!]").format(challenge=new_challenge)
                text = box(ANSITextColours.red.as_str(challenge_str), lang="ansi")
            elif monster_roster[challenge]["miniboss"]:
                timer = 60 * 3
                self.bot.dispatch("adventure_miniboss", ctx)
            else:
                timer = 60 * 2
            if transcended:
                self.bot.dispatch("adventure_transcended", ctx)
            elif "Ascended" in new_challenge:
                self.bot.dispatch("adventure_ascended", ctx)
            if attribute == "n immortal":
                self.bot.dispatch("adventure_immortal", ctx)
            elif attribute == " possessed":
                self.bot.dispatch("adventure_possessed", ctx)
        else:
            if transcended:
                new_challenge = challenge.replace("Ascended", "")
            timer = 60 * 3
            no_monster = random.randint(0, 100) == 25
        # if ctx.author.id in DEV_LIST:
        auto_users = self._adv_results.get_last_auto_users(ctx)
        for user in auto_users:
            try:
                c = await Character.from_json(ctx, self.config, user, self._daily_bonus)
                if c.do_not_disturb:
                    auto_users.remove(user)
            except Exception as exc:
                log.exception("Error with the new character sheet", exc_info=exc)
                continue
        #timer = 20
        self._sessions[ctx.guild.id] = GameSession(
            ctx=ctx,
            cog=self,
            challenge=new_challenge if not no_monster else None,
            attribute=attribute if not no_monster else None,
            guild=ctx.guild,
            boss=monster_roster[challenge]["boss"] if not no_monster else None,
            miniboss=monster_roster[challenge]["miniboss"] if not no_monster else None,
            timer=timer,
            monster=monster_roster[challenge] if not no_monster else None,
            monsters=monster_roster if not no_monster else None,
            message=ctx.message,
            transcended=transcended if not no_monster else None,
            monster_modified_stats=self._dynamic_monster_stats_simple(ctx, monster_roster[challenge], monster_stats),
            easy_mode=easy_mode,
            no_monster=no_monster,
            auto=auto_users
        )
        adventure_msg = (
            f"{adventure_msg}{text}\n{random.choice(self.LOCATIONS)}\n"
            f"{bold(ctx.author.display_name)}{random.choice(self.RAISINS)}"
        )
        await self._choice(ctx, adventure_msg)
        if ctx.guild.id not in self._sessions:
            return (None, None)
        rewards = self._rewards
        participants = self._sessions[ctx.guild.id].participants
        return (rewards, participants)

    async def _choice(self, ctx: commands.Context, adventure_msg):
        session = self._sessions[ctx.guild.id]
        easy_mode = session.easy_mode
        if easy_mode:
            dragon_text = _(
                "but **a{attr} {chall}** "
                "just landed in front of you glaring! \n\n"
                "What will you do and will other heroes be brave enough to help you?\n"
                "Heroes have 5 minutes to participate via reaction:"
                "\n\nReact with: {reactions}"
            ).format(
                attr=session.attribute,
                chall=session.challenge,
                reactions=_("**Attack** - **Magic** - **Talk** - **Pray**"),
            )
            basilisk_text = _(
                "but **a{attr} {chall}** stepped out looking around. \n\n"
                "What will you do and will other heroes help your cause?\n"
                "Heroes have 3 minutes to participate via reaction:"
                "\n\nReact with: {reactions}"
            ).format(
                attr=session.attribute,
                chall=session.challenge,
                reactions=_("**Attack** - **Magic** - **Talk** - **Pray**"),
            )
            normal_text = _(
                "but **a{attr} {chall}** "
                "is guarding it with{threat}. \n\n"
                "What will you do and will other heroes help your cause?\n"
                "Heroes have 2 minutes to participate via reaction:"
                "\n\nReact with: {reactions}"
            ).format(
                attr=session.attribute,
                chall=session.challenge,
                threat=random.choice(self.THREATEE),
                reactions=_("**Attack** - **Magic** - **Talk** - **Pray**"),
            )

            embed = discord.Embed(colour=discord.Colour.blurple())
            use_embeds = await self.config.guild(ctx.guild).embed() and ctx.channel.permissions_for(ctx.me).embed_links
            if session.boss:
                if use_embeds:
                    embed.description = f"{adventure_msg}\n{dragon_text}"
                    embed.colour = discord.Colour.dark_red()
                    if session.monster["image"]:
                        embed.set_image(url=session.monster["image"])
                    adventure_msg = await ctx.send(embed=embed, view=session)
                else:
                    adventure_msg = await ctx.send(f"{adventure_msg}\n{dragon_text}", view=session)
                timeout = 60 * 5

            elif session.miniboss:
                if use_embeds:
                    embed.description = f"{adventure_msg}\n{basilisk_text}"
                    embed.colour = discord.Colour.dark_green()
                    if session.monster["image"]:
                        embed.set_image(url=session.monster["image"])
                    adventure_msg = await ctx.send(embed=embed, view=session)
                else:
                    adventure_msg = await ctx.send(f"{adventure_msg}\n{basilisk_text}", view=session)
                timeout = 60 * 3
            else:
                if use_embeds:
                    embed.description = f"{adventure_msg}\n{normal_text}"
                    if session.monster["image"]:
                        embed.set_thumbnail(url=session.monster["image"])
                    adventure_msg = await ctx.send(embed=embed, view=session)
                else:
                    adventure_msg = await ctx.send(f"{adventure_msg}\n{normal_text}", view=session)
                timeout = 60 * 2
        else:
            embed = discord.Embed(colour=discord.Colour.blurple())
            use_embeds = await self.config.guild(ctx.guild).embed() and ctx.channel.permissions_for(ctx.me).embed_links
            timeout = 60 * 3
            obscured_text = _(
                "What will you do and will other heroes help your cause?\n"
                "Heroes have {time} minutes to participate via reaction:"
                "\n\nReact with: {reactions}"
            ).format(
                reactions=_("**Attack** - **Talk** - **Magic** - **Pray**"),
                time=timeout // 60,
            )
            if use_embeds:
                embed.description = f"{adventure_msg}\n{obscured_text}"
                adventure_msg = await ctx.send(embed=embed, view=session)
            else:
                adventure_msg = await ctx.send(f"{adventure_msg}\n{obscured_text}", view=session)

        session.message_id = adventure_msg.id
        session.message = adventure_msg
        # start_adding_reactions(adventure_msg, self._adventure_actions)
        timer = await self._adv_countdown(ctx, session.timer, "Time remaining")

        self.tasks[adventure_msg.id] = timer
        try:
            await asyncio.wait_for(timer, timeout=timeout + 5)
        except asyncio.TimeoutError:
            timer.cancel()
        except Exception as exc:
            timer.cancel()
            log.exception("Error with the countdown timer", exc_info=exc)
        await adventure_msg.edit(view=None)
        try:
            return await self._result(ctx, adventure_msg)
        except Exception:
            log.exception("Error in results")
            raise

    async def has_perm(self, user):
        if hasattr(self.bot, "allowed_by_whitelist_blacklist"):
            return await self.bot.allowed_by_whitelist_blacklist(user)
        else:
            return await self.local_perms(user) or await self.global_perms(user)

    async def local_perms(self, user):
        """Check the user is/isn't locally whitelisted/blacklisted.

        https://github.com/Cog-Creators/Red-DiscordBot/blob/V3/release/3.0.0/redbot/core/global_checks.py
        """
        if await self.bot.is_owner(user):
            return True
        guild_settings = self.bot.db.guild(user.guild)
        local_blacklist = await guild_settings.blacklist()
        local_whitelist = await guild_settings.whitelist()

        _ids = [r.id for r in user.roles if not r.is_default()]
        _ids.append(user.id)
        if local_whitelist:
            return any(i in local_whitelist for i in _ids)

        return not any(i in local_blacklist for i in _ids)

    async def global_perms(self, user):
        """Check the user is/isn't globally whitelisted/blacklisted.

        https://github.com/Cog-Creators/Red-DiscordBot/blob/V3/release/3.0.0/redbot/core/global_checks.py
        """
        if await self.bot.is_owner(user):
            return True
        whitelist = await self.bot.db.whitelist()
        if whitelist:
            return user.id in whitelist

        return user.id not in await self.bot.db.blacklist()

    @commands.Cog.listener()
    async def on_reaction_add(self, reaction: discord.Reaction, user: discord.Member):
        """This will be a cog level reaction_add listener for game logic."""
        await self.bot.wait_until_ready()
        if user.bot:
            return
        emojis = list(ReactionPredicate.NUMBER_EMOJIS) + self._adventure_actions
        if str(reaction.emoji) not in emojis:
            return
        if self.red_340_or_newer:
            if (guild := getattr(user, "guild", None)) is not None:
                if await self.bot.cog_disabled_in_guild(self, guild):
                    return
            else:
                return
        if not await self.has_perm(user):
            return
        if guild.id in self._sessions:
            if reaction.message.id == self._sessions[guild.id].message_id:
                if guild.id in self._adventure_countdown:
                    (timer, done, sremain) = self._adventure_countdown[guild.id]
                    if sremain > 3:
                        await self._handle_adventure(reaction, user)

    async def _handle_adventure(self, reaction: discord.Reaction, user: discord.Member):
        action = {v: k for k, v in self._adventure_controls.items()}[str(reaction.emoji)]
        session = self._sessions[user.guild.id]
        has_fund = await has_funds(user, 250)
        for x in ["fight", "magic", "talk", "pray", "run"]:
            if user in getattr(session, x, []):
                getattr(session, x).remove(user)

            if not has_fund or user in getattr(session, x, []):
                if reaction.message.channel.permissions_for(user.guild.me).manage_messages:
                    symbol = self._adventure_controls[x]
                    await reaction.message.remove_reaction(symbol, user)

        restricted = await self.config.restrict()
        if user not in getattr(session, action, []):
            if not has_fund:
                with contextlib.suppress(discord.HTTPException):
                    await user.send(
                        _(
                            "You contemplate going on an adventure with your friends, so "
                            "you go to your bank to get some money to prepare and they "
                            "tell you that your bank is empty!\n"
                            "You run home to look for some spare coins and you can't "
                            "even find a single one, so you tell your friends that you can't "
                            "join them as you already have plans... as you are too embarrassed "
                            "to tell them you are broke!"
                        )
                    )
                return
            if restricted:
                all_users = []
                for guild_id, guild_session in self._sessions.items():
                    guild_users_in_game = (
                        guild_session.fight
                        + guild_session.magic
                        + guild_session.talk
                        + guild_session.pray
                        + guild_session.run
                    )
                    all_users = all_users + guild_users_in_game

                if user in all_users:
                    user_id = f"{user.id}-{user.guild.id}"
                    # iterating through reactions here and removing them seems to be expensive
                    # so they can just keep their react on the adventures they can't join
                    if user_id not in self._react_messaged:
                        await reaction.message.channel.send(
                            _(
                                "{c}, you are already in an existing adventure. "
                                "Wait for it to finish before joining another one."
                            ).format(c=bold(user.display_name))
                        )
                        self._react_messaged.append(user_id)
                else:
                    getattr(session, action).append(user)
            else:
                getattr(session, action).append(user)

    async def get_treasure(
        self,
        session: GameSession,
        hp: int,
        dipl: int,
        slain: bool = False,
        persuaded: bool = False,
        failed: bool = False,
        crit_bonus: bool = False,
    ) -> Treasure:
        if session.no_monster:
            available_loot = [
                Treasure(_set=1),
                Treasure(ascended=1, _set=2),
                Treasure(epic=3, legendary=1),
                Treasure(legendary=3, ascended=2),
                Treasure(epic=1, legendary=3, _set=1),
                Treasure(epic=1, legendary=2, ascended=1),
                Treasure(epic=1, legendary=5, ascended=2, _set=1),
                Treasure(epic=1, legendary=5, ascended=1, _set=1),
                Treasure(epic=1, legendary=1, ascended=1, _set=1),
            ]
            treasure = random.choice(available_loot)
            return treasure
        treasure = Treasure()  # empty treasure container
        if (slain or persuaded) and not failed:
            roll = random.randint(1, 10)
            monster_amount = hp + dipl if slain and persuaded else hp if slain else dipl
            if session.transcended:
                if session.boss and not session.no_monster:
                    available_loot = [
                        Treasure(epic=1, legendary=5, ascended=2, _set=3),
                        Treasure(epic=2, legendary=6, ascended=1, _set=3),
                        Treasure(epic=3, legendary=7, ascended=1, _set=3),
                    ]
                else:
                    available_loot = [
                        Treasure(epic=1, legendary=5, ascended=1, _set=1),
                        Treasure(epic=2, legendary=3, _set=1),
                        Treasure(epic=3, legendary=1, ascended=1, _set=1),
                        Treasure(epic=1, legendary=5, _set=1),
                    ]
                treasure = random.choice(available_loot)
            elif session.boss:
                available_loot = [
                    Treasure(epic=3, legendary=5, _set=1),
                    Treasure(epic=1, legendary=2, ascended=1, _set=1),
                    Treasure(legendary=3, ascended=2, _set=1),
                ]
                treasure = random.choice(available_loot)
            elif session.miniboss:
                available_loot = [
                    Treasure(epic=4, ascended=2),
                    Treasure(epic=2, legendary=1, ascended=2),
                    Treasure(epic=3, legendary=2),
                    Treasure(rare=6, legendary=3, ascended=2),
                ]
                treasure = random.choice(available_loot)
            elif monster_amount >= 8000:
                available_loot = [
                    Treasure(epic=3, legendary=3, ascended=1),
                    Treasure(epic=1, legendary=5),
                    Treasure(epic=1, legendary=2, ascended=1),
                ]
                treasure = random.choice(available_loot)
            elif monster_amount >= 6000:
                available_loot = [
                    Treasure(epic=3, legendary=3),
                    Treasure(epic=1, legendary=1, ascended=1),
                    Treasure(legendary=2, ascended=1),
                ]
                if roll <= 9:
                    treasure = random.choice(available_loot)
            elif monster_amount >= 5000:
                available_loot = [
                    Treasure(epic=3, legendary=3),
                    Treasure(epic=1, legendary=1, ascended=1),
                    Treasure(legendary=2, ascended=1),
                ]
                if roll <= 7:
                    treasure = random.choice(available_loot)
            elif monster_amount >= 3000:
                available_loot = [
                    Treasure(epic=3, legendary=1),
                    Treasure(epic=1, legendary=2),
                    Treasure(legendary=1, ascended=1),
                ]
                if roll <= 7:
                    treasure = random.choice(available_loot)
            elif monster_amount >= 1500:
                available_loot = [
                    Treasure(rare=1, epic=3),
                    Treasure(rare=5, epic=1),
                    Treasure(epic=2, legendary=1),
                ]
                if roll <= 7:
                    treasure = random.choice(available_loot)
            elif monster_amount >= 700:
                available_loot = [
                    Treasure(epic=1),
                    Treasure(rare=1),
                    Treasure(legendary=1),
                ]
                if roll <= 7:
                    treasure = random.choice(available_loot)
            elif monster_amount >= 500:
                available_loot = [
                    Treasure(epic=1),
                    Treasure(rare=1),
                    Treasure(rare=1, epic=1),
                ]
                if roll <= 5:
                    treasure = random.choice(available_loot)
            elif monster_amount >= 300:
                available_loot = [
                    Treasure(normal=1),
                    Treasure(rare=1),
                    Treasure(normal=1, rare=1),
                ]
                if roll <= 2:
                    treasure = random.choice(available_loot)
            elif monster_amount >= 80:
                if roll == 1:
                    treasure = Treasure(normal=1)
            if crit_bonus:
                treasure.epic += 1
            if not treasure:
                treasure = Treasure()
        return treasure

    async def _result(self, ctx: commands.Context, message: discord.Message):
        if ctx.guild.id not in self._sessions:
            log.debug("Session not found for %s", ctx.guild.id)
            return
        calc_msg = await ctx.send(_("Calculating..."))
        attack = 0
        diplomacy = 0
        magic = 0
        fumblelist: list = []
        critlist: list = []
        failed = False
        lost = False
        with contextlib.suppress(discord.HTTPException):
            await message.clear_reactions()
        session = self._sessions[ctx.guild.id]
        challenge = session.challenge
        fight_list = list(set(session.fight))
        talk_list = list(set(session.talk))
        pray_list = list(set(session.pray))
        magic_list = list(set(session.magic))
        auto_list = list(set(session.auto))

        self._sessions[ctx.guild.id].fight = fight_list
        self._sessions[ctx.guild.id].talk = talk_list
        self._sessions[ctx.guild.id].pray = pray_list
        self._sessions[ctx.guild.id].magic = magic_list
        self._sessions[ctx.guild.id].auto = auto_list
        fight_name_list = []
        wizard_name_list = []
        talk_name_list = []
        pray_name_list = []
        repair_list = []
        for user in fight_list:
            fight_name_list.append(f"{bold(user.display_name)}")
        for user in magic_list:
            wizard_name_list.append(f"{bold(user.display_name)}")
        for user in talk_list:
            talk_name_list.append(f"{bold(user.display_name)}")
        for user in pray_list:
            pray_name_list.append(f"{bold(user.display_name)}")

        fighters_final_string = _(" and ").join(
            [", ".join(fight_name_list[:-1]), fight_name_list[-1]] if len(fight_name_list) > 2 else fight_name_list
        )
        wizards_final_string = _(" and ").join(
            [", ".join(wizard_name_list[:-1]), wizard_name_list[-1]] if len(wizard_name_list) > 2 else wizard_name_list
        )
        talkers_final_string = _(" and ").join(
            [", ".join(talk_name_list[:-1]), talk_name_list[-1]] if len(talk_name_list) > 2 else talk_name_list
        )
        preachermen_final_string = _(" and ").join(
            [", ".join(pray_name_list[:-1]), pray_name_list[-1]] if len(pray_name_list) > 2 else pray_name_list
        )
        if session.no_monster:
            treasure = await self.get_treasure(session, 0, 0)

            session.participants = set(fight_list + magic_list + talk_list + pray_list + auto_list + fumblelist)

            participants = {
                "fight": fight_list,
                "spell": magic_list,
                "talk": talk_list,
                "pray": pray_list,
                "auto": auto_list,
                "fumbles": fumblelist,
            }
            text = ""
            text += await self._reward(
                ctx,
                [u for u in fight_list + magic_list + pray_list + talk_list + auto_list if u not in fumblelist],
                500 + int(500 * (0.25 * len(session.participants))),
                0,
                treasure,
            )
            parsed_users = []

            for action_name, action in participants.items():
                for user in action:
                    try:
                        c = await Character.from_json(ctx, self.config, user, self._daily_bonus)
                    except Exception as exc:
                        log.exception("Error with the new character sheet", exc_info=exc)
                        continue
                    current_val = c.adventures.get(action_name, 0)

                    c.adventures.update({action_name: current_val + 1})
                    if user not in parsed_users:
                        special_action = "loses" if lost else "wins"
                        current_val = c.adventures.get(special_action, 0)
                        c.adventures.update({special_action: current_val + 1})
                        c.weekly_score.update({"adventures": c.weekly_score.get("adventures", 0) + 1})
                        parsed_users.append(user)
                    await self.config.user(user).set(await c.to_json(ctx, self.config))

            output = _(
                "All adventurers prepared for an epic adventure, but they soon realise all this treasure was unprotected!\n{text}"
            ).format(
                text=text
            )
            output = pagify(output, page_length=1900)
            await calc_msg.delete()
            for i in output:
                await smart_embed(ctx, i, success=True)
            return

        people = len(fight_list) + len(magic_list) + len(talk_list) + len(pray_list) + len(auto_list)
        failed = await self.handle_basilisk(ctx)
        handled_pray_list, fumblelist, attack, diplomacy, magic, pray_msg = await self.handle_pray(
            ctx.guild.id, fumblelist, attack, diplomacy, magic
        )
        handled_talk_list, fumblelist, critlist, diplomacy, talk_msg = await self.handle_talk(
            ctx.guild.id, fumblelist, critlist, diplomacy
        )
        handled_fight_list, handled_magic_list, fumblelist, critlist, attack, magic, fight_msg = await self.handle_fight(
            ctx.guild.id, fumblelist, critlist, attack, magic
        )
        result_msg = pray_msg + talk_msg + fight_msg
        challenge_attrib = session.attribute
        hp = max(
            int(session.monster_modified_stats["hp"] * self.ATTRIBS[challenge_attrib][0]), 1
        )
        dipl = max(
            int(session.monster_modified_stats["dipl"] * self.ATTRIBS[challenge_attrib][1]), 1
        )

        dmg_dealt = int(attack + magic)
        diplomacy = int(diplomacy)
        slain = dmg_dealt >= int(hp)
        persuaded = diplomacy >= int(dipl)
        crit_bonus = len(critlist) != 0
        damage_str = ""
        diplo_str = ""
        if dmg_dealt > 0:
            damage_str = _("The group {status} {challenge} **({result}/{int_hp})**.\n").format(
                status=_("hit the") if failed or not slain else _("killed the"),
                challenge=bold(challenge),
                result=humanize_number(dmg_dealt),
                int_hp=humanize_number(hp),
            )
        if diplomacy > 0:
            diplo_str = _("The group {status} the {challenge} with {how} **({diplomacy}/{int_dipl})**.\n").format(
                status=_("tried to persuade") if not persuaded else _("distracted"),
                challenge=bold(challenge),
                how=_("flattery") if failed or not persuaded else _("insults"),
                diplomacy=humanize_number(diplomacy),
                int_dipl=humanize_number(dipl),
            )

        result_msg = result_msg + "\n" + damage_str + diplo_str
        await calc_msg.delete()
        text = ""
        success = False
        if (slain or persuaded) and not failed:
            success = True
        # treasure = [0, 0, 0, 0, 0, 0]
        treasure = await self.get_treasure(session, hp, dipl, slain, persuaded, failed, crit_bonus)
        if session.miniboss and failed:
            session.participants = set(fight_list + talk_list + pray_list + magic_list + auto_list + fumblelist)
            currency_name = await bank.get_currency_name(
                ctx.guild,
            )
            for user in session.participants:
                try:
                    c = await Character.from_json(ctx, self.config, user, self._daily_bonus)
                except Exception as exc:
                    log.exception("Error with the new character sheet", exc_info=exc)
                    continue
                if c.bal > 0:
                    multiplier = 1 / 3 if c.rebirths >= 10 else 0.01
                    if c._dex < 0:
                        dex = min(1 / abs(c._dex), 1)
                    else:
                        dex = max(c._dex // 10, 1)
                    multiplier = multiplier / dex
                    loss = round(c.bal * multiplier)
                    pet_loss = self.roll_pet_gold_loss(c, loss)
                    total_loss = loss + pet_loss
                    if total_loss > c.bal:
                        total_loss = c.bal
                    if user not in [u for u, a, b in repair_list]:
                        repair_list.append([user, loss, pet_loss])
                        if c.bal > total_loss:
                            await bank.withdraw_credits(user, total_loss)
                        else:
                            await bank.set_balance(user, 0)
                c.adventures.update({"loses": c.adventures.get("loses", 0) + 1})
                c.weekly_score.update({"adventures": c.weekly_score.get("adventures", 0) + 1})
                await self.config.user(user).set(await c.to_json(ctx, self.config))
            loss_list = []
            result_msg += session.miniboss["defeat"]
            if len(repair_list) > 0:
                temp_repair = []
                for user, loss, pet_loss in repair_list:
                    if user not in temp_repair:
                        loss_list.append(
                            _("\n{user} used {loss} {currency_name}").format(
                                user=user.mention,
                                loss=humanize_number(loss),
                                currency_name=currency_name,
                            )
                        )
                        if pet_loss > 0:
                            loss_list.append(
                                _("\n{user} used {pet_loss} {currency_name} to tend to their pet").format(
                                    user=user.mention,
                                    pet_loss=humanize_number(pet_loss),
                                    currency_name=currency_name,
                                )
                            )
                        temp_repair.append(user)
                if loss_list:
                    self._loss_message[ctx.message.id] = humanize_list(loss_list).strip()
            return await smart_embed(ctx, result_msg)
        if session.miniboss and not slain and not persuaded:
            lost = True
            session.participants = set(fight_list + talk_list + pray_list + magic_list + auto_list + fumblelist)
            currency_name = await bank.get_currency_name(
                ctx.guild,
            )
            for user in session.participants:
                try:
                    c = await Character.from_json(ctx, self.config, user, self._daily_bonus)
                except Exception as exc:
                    log.exception("Error with the new character sheet", exc_info=exc)
                    continue
                if c.bal > 0:
                    multiplier = 1 / 3 if c.rebirths >= 10 else 0.01
                    if c._dex < 0:
                        dex = min(1 / abs(c._dex), 1)
                    else:
                        dex = max(c._dex // 10, 1)
                    multiplier = multiplier / dex
                    loss = round(c.bal * multiplier)
                    pet_loss = self.roll_pet_gold_loss(c, loss)
                    total_loss = loss + pet_loss
                    if total_loss > c.bal:
                        total_loss = c.bal
                    if user not in [u for u, a, b in repair_list]:
                        repair_list.append([user, loss, pet_loss])
                        if c.bal > total_loss:
                            await bank.withdraw_credits(user, total_loss)
                        else:
                            await bank.set_balance(user, 0)
            loss_list = []
            if len(repair_list) > 0:
                temp_repair = []
                for user, loss, pet_loss in repair_list:
                    if user not in temp_repair:
                        loss_list.append(
                            _("\n{user} used {loss} {currency_name}").format(
                                user=user.mention,
                                loss=humanize_number(loss),
                                currency_name=currency_name,
                            )
                        )
                        if pet_loss > 0:
                            loss_list.append(
                                _("\n{user} used {pet_loss} {currency_name} to tend to their pet").format(
                                    user=user.mention,
                                    pet_loss=humanize_number(pet_loss),
                                    currency_name=currency_name,
                                )
                            )
                        temp_repair.append(user)
                if loss_list:
                    self._loss_message[ctx.message.id] = humanize_list(loss_list).strip()
            miniboss = session.challenge
            special = session.miniboss["special"]
            result_msg += _("The {miniboss}'s {special} was countered, but they still managed to kill you.").format(
                miniboss=bold(miniboss), special=special
            )
        amount = 1
        amount *= (hp + dipl) if slain and persuaded else hp if slain else dipl
        amount += int(amount * (0.25 * people))
        currency_name = await bank.get_currency_name(ctx.guild)
        if people == 1:
            if slain:
                group = fighters_final_string if len(handled_fight_list) == 1 else wizards_final_string
                text = _("{b_group} has slain the {chall} in an epic battle!").format(
                    b_group=group, chall=session.challenge
                )
                text += await self._reward(
                    ctx,
                    [u for u in handled_fight_list + handled_magic_list + handled_pray_list if u not in fumblelist],
                    amount,
                    round(((attack if group == fighters_final_string else magic) / hp) * 0.25),
                    treasure,
                )

            if persuaded:
                text = _("{b_talkers} almost died in battle, but confounded the {chall} in the last second.").format(
                    b_talkers=talkers_final_string, chall=session.challenge
                )
                text += await self._reward(
                    ctx,
                    [u for u in handled_talk_list + handled_pray_list if u not in fumblelist],
                    amount,
                    round((diplomacy / dipl) * 0.25),
                    treasure,
                )

            if not slain and not persuaded:
                lost = True
                currency_name = await bank.get_currency_name(
                    ctx.guild,
                )
                users = set(fight_list + magic_list + talk_list + pray_list + auto_list + fumblelist)
                for user in users:
                    try:
                        c = await Character.from_json(ctx, self.config, user, self._daily_bonus)
                    except Exception as exc:
                        log.exception("Error with the new character sheet", exc_info=exc)
                        continue
                    if c.bal > 0:
                        multiplier = 1 / 3 if c.rebirths >= 10 else 0.01
                        if c._dex < 0:
                            dex = min(1 / abs(c._dex), 1)
                        else:
                            dex = max(c._dex // 10, 1)
                        multiplier = multiplier / dex
                        loss = round(c.bal * multiplier)
                        pet_loss = self.roll_pet_gold_loss(c, loss)
                        total_loss = loss + pet_loss
                        if total_loss > c.bal:
                            total_loss = c.bal
                        if user not in [u for u, a, b in repair_list]:
                            repair_list.append([user, loss, pet_loss])
                            if c.bal > loss:
                                await bank.withdraw_credits(user, total_loss)
                            else:
                                await bank.set_balance(user, 0)
                loss_list = []
                if len(repair_list) > 0:
                    temp_repair = []
                    for user, loss, pet_loss in repair_list:
                        if user not in temp_repair:
                            loss_list.append(
                                _("\n{user} used {loss} {currency_name}").format(
                                    user=user.mention,
                                    loss=humanize_number(loss),
                                    currency_name=currency_name,
                                )
                            )
                            if pet_loss > 0:
                                loss_list.append(
                                    _("\n{user} used {pet_loss} {currency_name} to tend to their pet").format(
                                        user=user.mention,
                                        pet_loss=humanize_number(pet_loss),
                                        currency_name=currency_name,
                                    )
                                )
                            temp_repair.append(user)
                    if loss_list:
                        self._loss_message[ctx.message.id] = humanize_list(loss_list).strip()
                options = [
                    _("No amount of diplomacy or valiant fighting could save you."),
                    _("This challenge was too much for one hero."),
                    _("You tried your best, but the group couldn't succeed at their attempt."),
                ]
                text = random.choice(options)
        else:
            if slain and persuaded:
                if len(pray_list) > 0:
                    god = await self.config.god_name()
                    if await self.config.guild(ctx.guild).god_name():
                        god = await self.config.guild(ctx.guild).god_name()
                    if len(handled_magic_list) > 0 and len(handled_fight_list) > 0:
                        text = _(
                            "{b_fighters} slayed the {chall} "
                            "in battle, while {b_talkers} distracted with flattery, "
                            "{b_wizard} chanted magical incantations and "
                            "{b_preachers} aided in {god}'s name."
                        ).format(
                            b_fighters=fighters_final_string,
                            chall=session.challenge,
                            b_talkers=talkers_final_string,
                            b_wizard=wizards_final_string,
                            b_preachers=preachermen_final_string,
                            god=god,
                        )
                    else:
                        group = fighters_final_string if len(handled_fight_list) > 0 else wizards_final_string
                        text = _(
                            "{b_group} slayed the {chall} "
                            "in battle, while {b_talkers} distracted with flattery and "
                            "{b_preachers} aided in {god}'s name."
                        ).format(
                            b_group=group,
                            chall=session.challenge,
                            b_talkers=talkers_final_string,
                            b_preachers=preachermen_final_string,
                            god=god,
                        )
                else:
                    if len(handled_magic_list) > 0 and len(handled_fight_list) > 0:
                        text = _(
                            "{b_fighters} slayed the {chall} "
                            "in battle, while {b_talkers} distracted with insults and "
                            "{b_wizard} chanted magical incantations."
                        ).format(
                            b_fighters=fighters_final_string,
                            chall=session.challenge,
                            b_talkers=talkers_final_string,
                            b_wizard=wizards_final_string,
                        )
                    else:
                        group = fighters_final_string if len(handled_fight_list) > 0 else wizards_final_string
                        text = _(
                            "{b_group} slayed the {chall} in battle, while {b_talkers} distracted with insults."
                        ).format(b_group=group, chall=session.challenge, b_talkers=talkers_final_string)
                text += await self._reward(
                    ctx,
                    [u for u in handled_fight_list + handled_magic_list + handled_pray_list + handled_talk_list if u not in fumblelist],
                    amount,
                    round(((dmg_dealt / hp) + (diplomacy / dipl)) * 0.25),
                    treasure,
                )

            if not slain and persuaded:
                if len(pray_list) > 0:
                    text = _("{b_talkers} talked the {chall} down with {b_preachers}'s blessing.").format(
                        b_talkers=talkers_final_string,
                        chall=session.challenge,
                        b_preachers=preachermen_final_string,
                    )
                else:
                    text = _("{b_talkers} talked the {chall} down.").format(
                        b_talkers=talkers_final_string, chall=session.challenge
                    )
                text += await self._reward(
                    ctx,
                    [u for u in handled_talk_list + handled_pray_list if u not in fumblelist],
                    amount,
                    round((diplomacy / dipl) * 0.25),
                    treasure,
                )

            if slain and not persuaded:
                if len(handled_pray_list) > 0:
                    if len(handled_magic_list) > 0 and len(handled_fight_list) > 0:
                        text = _(
                            "{b_fighters} killed the {chall} "
                            "in a most heroic battle with a little help from {b_preachers} and "
                            "{b_wizard} chanting magical incantations."
                        ).format(
                            b_fighters=fighters_final_string,
                            chall=session.challenge,
                            b_preachers=preachermen_final_string,
                            b_wizard=wizards_final_string,
                        )
                    else:
                        group = fighters_final_string if len(handled_fight_list) > 0 else wizards_final_string
                        text = _(
                            "{b_group} killed the {chall} "
                            "in a most heroic battle with a little help from {b_preachers}."
                        ).format(
                            b_group=group,
                            chall=session.challenge,
                            b_preachers=preachermen_final_string,
                        )
                else:
                    if len(handled_magic_list) > 0 and len(handled_fight_list) > 0:
                        text = _(
                            "{b_fighters} killed the {chall} "
                            "in a most heroic battle with {b_wizard} chanting magical incantations."
                        ).format(
                            b_fighters=fighters_final_string,
                            chall=session.challenge,
                            b_wizard=wizards_final_string,
                        )
                    else:
                        group = fighters_final_string if len(handled_fight_list) > 0 else wizards_final_string
                        text = _("{b_group} killed the {chall} in an epic fight.").format(
                            b_group=group, chall=session.challenge
                        )
                text += await self._reward(
                    ctx,
                    [u for u in handled_fight_list + handled_magic_list + handled_pray_list if u not in fumblelist],
                    amount,
                    round((dmg_dealt / hp) * 0.25),
                    treasure,
                )

            if not slain and not persuaded:
                lost = True
                currency_name = await bank.get_currency_name(
                    ctx.guild,
                )
                users = set(handled_fight_list + handled_magic_list + handled_talk_list + handled_pray_list + fumblelist)
                for user in users:
                    try:
                        c = await Character.from_json(ctx, self.config, user, self._daily_bonus)
                    except Exception as exc:
                        log.exception("Error with the new character sheet", exc_info=exc)
                        continue
                    if c.bal > 0:
                        multiplier = 1 / 3 if c.rebirths >= 10 else 0.01
                        if c._dex < 0:
                            dex = min(1 / abs(c._dex), 1)
                        else:
                            dex = max(c._dex // 10, 1)
                        multiplier = multiplier / dex
                        loss = round(c.bal * multiplier)
                        pet_loss = self.roll_pet_gold_loss(c, loss)
                        total_loss = loss + pet_loss
                        if total_loss > c.bal:
                            total_loss = c.bal
                        if user not in [u for u, a, b in repair_list]:
                            repair_list.append([user, loss, pet_loss])
                            if c.bal > total_loss:
                                await bank.withdraw_credits(user, total_loss)
                            else:
                                await bank.set_balance(user, 0)
                options = [
                    _("No amount of diplomacy or valiant fighting could save you."),
                    _("This challenge was too much for the group."),
                    _("You tried your best, but couldn't succeed."),
                ]
                text = random.choice(options)
        loss_list = []
        if len(repair_list) > 0:
            temp_repair = []
            for user, loss, pet_loss in repair_list:
                if user not in temp_repair:
                    loss_list.append(
                        _("\n{user} used {loss} {currency_name}").format(
                            user=user.mention,
                            loss=humanize_number(loss),
                            currency_name=currency_name,
                        )
                    )
                    if pet_loss > 0:
                        loss_list.append(
                            _("\n{user} used {pet_loss} {currency_name} to tend to their pet").format(
                                user=user.mention,
                                pet_loss=humanize_number(pet_loss),
                                currency_name=currency_name,
                            )
                        )
                    temp_repair.append(user)
            if loss_list:
                self._loss_message[ctx.message.id] = humanize_list(loss_list).strip()
        output = f"{result_msg}\n{text}"
        output = pagify(output, page_length=1900)
        img_sent = session.monster["image"] if not session.easy_mode else None
        for i in output:
            await smart_embed(ctx, i, success=success, image=img_sent)
            if img_sent:
                img_sent = None
        await self._data_check(ctx)
        session.participants = set(fight_list + magic_list + talk_list + pray_list + auto_list + fumblelist)

        participants = {
            "fight": fight_list,
            "spell": magic_list,
            "talk": talk_list,
            "pray": pray_list,
            "auto": auto_list,
            "fumbles": fumblelist,
        }
        parsed_users = []
        do_not_disturbed_users = []
        for action_name, action in participants.items():
            for user in action:
                try:
                    c = await Character.from_json(ctx, self.config, user, self._daily_bonus)
                except Exception as exc:
                    log.exception("Error with the new character sheet", exc_info=exc)
                    continue
                if c.do_not_disturb:
                    do_not_disturbed_users.append(user)
                current_val = c.adventures.get(action_name, 0)
                c.adventures.update({action_name: current_val + 1})
                if user not in parsed_users:
                    special_action = "loses" if lost else "wins"
                    current_val = c.adventures.get(special_action, 0)
                    c.adventures.update({special_action: current_val + 1})
                    c.weekly_score.update({"adventures": c.weekly_score.get("adventures", 0) + 1})
                    parsed_users.append(user)
                await self.config.user(user).set(await c.to_json(ctx, self.config))

        manual_participants = fight_list + talk_list + magic_list + pray_list
        if dmg_dealt >= diplomacy:
            self._adv_results.add_result(ctx, "attack", dmg_dealt, people, slain, manual_participants, auto_list,
                                         do_not_disturbed_users)
        else:
            self._adv_results.add_result(ctx, "talk", diplomacy, people, persuaded, manual_participants, auto_list,
                                         do_not_disturbed_users)

    async def handle_run(self, guild_id, attack, diplomacy, magic, shame=False):
        runners = []
        msg = ""
        session = self._sessions[guild_id]
        if len(list(session.run)) != 0:
            for user in session.run:
                runners.append(f"{bold(user.display_name)}")
            msg += _("{} just ran away.\n").format(humanize_list(runners))
            if shame:
                msg += _(
                    "They are now regretting their pathetic display of courage as their friends enjoy all their new loot.\n"
                )
        return (attack, diplomacy, magic, msg)

    @staticmethod
    def roll_pet_crit(c, roll, max_roll):
        new_roll = roll
        roll_perc = roll / max_roll
        if c.hc == HeroClasses.ranger and c.heroclass.get("pet", {}).get("bonuses", {}).get("crit", False):
            pet_crit = c.heroclass.get("pet", {}).get("bonuses", {}).get("crit", 0)
            pet_crit = random.randint(pet_crit, 100)
            if pet_crit == 100:
                # pet full crit roll, player also gets full crit roll
                new_roll = max_roll
            elif roll_perc > 0.95 and pet_crit >= 95:
                # both player and pet crit, chance to re-roll for higher dmg
                new_roll = random.randint(roll, max_roll)
            elif pet_crit >= 95:
                # pet crit but player did not, player re-roll with old roll as new baseline
                new_roll = random.randint(roll, max_roll)
        return new_roll

    @staticmethod
    def roll_pet_gold_loss(c, loss):
        pet_loss = 0
        roll = random.randint(1, 100)
        target_number = 45
        if c.heroclass.get("pet", {}).get("bonuses", {}).get("always", False):
            roll = 1  # pick 1 to guarantee bonus if pet allows it
        if roll < target_number and c.heroclass["pet"]:
            pet_loss = round((loss * (c.heroclass["pet"]["bonus"] - 1)) / 2)
        return pet_loss

    async def handle_fight(self, guild_id, fumblelist, critlist, attack, magic):
        session = self._sessions[guild_id]
        ctx = session.ctx
        fight_list = list(set(session.fight))
        magic_list = list(set(session.magic))

        len_fight_list = len(session.fight)
        len_magic_list = len(session.magic)

        if len_fight_list >= len(session.magic) and len_fight_list >= len(session.talk):
            fight_list += await self.filter_clerics_from_auto(ctx)
        elif len_magic_list > len(session.fight) and len_magic_list >= len(session.talk):
            magic_list += await self.filter_clerics_from_auto(ctx)

        attack_list = list(set(fight_list + magic_list))
        pdef = max(session.monster_modified_stats["pdef"], 0.5)
        mdef = max(session.monster_modified_stats["mdef"], 0.5)

        fumble_count = 0
        # make sure we pass this check first
        failed_emoji = self.emojis.fumble
        if len(attack_list) >= 1:
            msg = ""
            report = _("Attack Party: \n\n")
        else:
            return (fight_list, magic_list, fumblelist, critlist, attack, magic, "")

        for user in fight_list:
            try:
                c = await Character.from_json(ctx, self.config, user, self._daily_bonus)
            except Exception as exc:
                log.exception("Error with the new character sheet", exc_info=exc)
                continue
            crit_mod = max(max(c.dex, c.luck // 2) + (c.total_att // 20), 0)  # Thanks GoaFan77
            mod = 0
            max_roll = 100 if c.rebirths >= 30 else 50 if c.rebirths >= 15 else 20
            if crit_mod != 0:
                mod = round(crit_mod / 10)
            if c.rebirths < 15 < mod:
                mod = 15
                max_roll = 20
            elif (mod + 1) > 45:
                mod = 45

            roll = max(random.randint((1 + mod), max_roll), 1)
            roll = self.roll_pet_crit(c, roll, max_roll)
            roll_perc = roll / max_roll

            att_value = c.total_att
            rebirths = c.rebirths * (3 if c.hc is HeroClasses.berserker else 2 if c.hc is HeroClasses.ranger else 1)
            if roll_perc < 0.10 or (roll + att_value) <= 0:
                if c.hc is HeroClasses.berserker and c.heroclass["ability"]:
                    bonus_roll = random.randint(5, max(15, c.rebirths))
                    bonus_multi = random.choice([0.2, 0.3, 0.4, 0.5])
                    bonus = max(bonus_roll, int((roll + att_value + rebirths) * bonus_multi))
                    attack += int((roll - bonus + att_value) / pdef)  # no pierce bonus for berserker if they fumble
                    report += (
                        f"{bold(user.display_name)}: "
                        f"{self.emojis.dice}({roll}) + "
                        f"{self.emojis.berserk}{humanize_number(bonus)} + "
                        f"{self.emojis.attack}{str(humanize_number(att_value))}\n"
                    )
                else:
                    msg += _("{user} fumbled the attack.\n").format(user=bold(user.display_name))
                    fumblelist.append(user)
                    fumble_count += 1
            elif roll_perc > 0.95 or c.hc in [HeroClasses.berserker, HeroClasses.ranger]:
                crit_str = ""
                crit_bonus = 0
                base_bonus = random.randint(5, max(15, c.rebirths)) + rebirths
                ability_used = False
                if roll_perc > 0.95:
                    msg += _("{user} landed a critical hit.\n").format(user=bold(user.display_name))
                    critlist.append(user)
                    crit_bonus = (random.randint(5, 20)) + (rebirths * 2)
                    crit_str = f"{self.emojis.crit}{humanize_number(crit_bonus)}"

                if c.hc in [HeroClasses.berserker, HeroClasses.ranger] and c.heroclass["ability"]:
                    ability_used = True
                    base_bonus = (random.randint(1, max(15, c.rebirths)) + 5) * (rebirths // 2)

                if c.hc == HeroClasses.berserker:
                    base_str = f"{self.emojis.berserk}{humanize_number(base_bonus)}"
                elif c.hc == HeroClasses.ranger:
                    base_str = f"🏹{humanize_number(base_bonus)}"
                else:
                    base_str = f"{self.emojis.crit}{humanize_number(base_bonus)}"

                if ability_used:
                    if c.hc == HeroClasses.berserker and c.rebirths >= HC_VETERAN_RANK:
                        attack += int((roll + crit_bonus + att_value) / pdef) + int(base_bonus)
                        base_str = f"{self.emojis.berserk}{humanize_number(base_bonus)} PIERCE!"
                    elif c.hc == HeroClasses.ranger:
                        bonus_mod = 0.35 if c.rebirths >= HC_VETERAN_RANK else 0.25
                        num_hits = random.randint(3, 8) if c.rebirths >= HC_VETERAN_RANK else random.randint(3, 6)
                        dmg_bonus = round(base_bonus * bonus_mod)
                        attack += int((roll + crit_bonus + (dmg_bonus * num_hits) + att_value) / pdef)
                        base_str = f"🏹{humanize_number(dmg_bonus)} x {num_hits}"
                else:
                    attack += int((roll + base_bonus + crit_bonus + att_value) / pdef)
                bonus = f"{crit_str} + {base_str}" if crit_str else f"{base_str}"
                report += (
                    f"{bold(user.display_name)}: "
                    f"{self.emojis.dice}({roll}) + "
                    f"{bonus} + "
                    f"{self.emojis.attack}{str(humanize_number(att_value))}\n"
                )
            else:
                attack += int((roll + att_value) / pdef) + rebirths
                report += (
                    f"{bold(user.display_name)}: "
                    f"{self.emojis.dice}({roll}) + "
                    f"{self.emojis.attack}{str(humanize_number(att_value))}\n"
                )
            if session.insight[0] == 1 and user.id != session.insight[1].user.id:
                attack += int(session.insight[1].total_att * 0.2)
        for user in magic_list:
            try:
                c = await Character.from_json(ctx, self.config, user, self._daily_bonus)
            except Exception as exc:
                log.exception("Error with the new character sheet", exc_info=exc)
                continue
            crit_mod = max(max(c.dex, c.luck // 2) + (c.total_int // 20), 0)
            mod = 0
            max_roll = 100 if c.rebirths >= 30 else 50 if c.rebirths >= 15 else 20
            if crit_mod != 0:
                mod = round(crit_mod / 10)
            if c.rebirths < 15 < mod:
                mod = 15
                max_roll = 20
            elif (mod + 1) > 45:
                mod = 45

            roll = max(random.randint((1 + mod), max_roll), 1)
            roll_perc = roll / max_roll

            int_value = c.total_int
            rebirths = c.rebirths * (3 if c.hc is HeroClasses.wizard else 1)
            if roll_perc < 0.10 or (roll + int_value) <= 0:
                # fumble condition
                msg += _("{}{} almost set themselves on fire.\n").format(failed_emoji, bold(user.display_name))
                fumblelist.append(user)
                fumble_count += 1
                if c.hc is HeroClasses.wizard and c.heroclass["ability"]:
                    # wizard ability used but fumbled the roll, still give bonus but at a reduced rate
                    bonus_roll = random.randint(5, max(15, c.rebirths))
                    bonus_multi = random.choice([0.2, 0.3, 0.4, 0.5])
                    bonus = max(bonus_roll, int((roll + int_value + rebirths) * bonus_multi))
                    if c.rebirths < HC_VETERAN_RANK:
                        magic += int((roll - bonus + int_value) / mdef)
                        report += (
                            f"{bold(user.display_name)}: "
                            f"{self.emojis.dice}({roll}) + "
                            f"{self.emojis.magic_crit}{humanize_number(bonus)} + "
                            f"{self.emojis.magic}{str(humanize_number(int_value))}\n"
                        )
                    else:
                        double_cast_bonus = round(0.20 * bonus)
                        magic += int((roll - bonus + double_cast_bonus + int_value) / mdef)
                        report += (
                            f"{bold(user.display_name)}: "
                            f"{self.emojis.dice}({roll}) + "
                            f"{self.emojis.magic_crit}{humanize_number(bonus)} + "
                            f"{self.emojis.magic_crit}{humanize_number(double_cast_bonus)} + "
                            f"{self.emojis.magic}{str(humanize_number(int_value))}\n"
                        )
            elif roll_perc > 0.95 or (c.hc is HeroClasses.wizard):
                crit_str = ""
                crit_bonus = 0
                double_cast_bonus = 0
                base_bonus = random.randint(5, max(15, c.rebirths)) + rebirths
                base_str = f"{self.emojis.magic_crit}️{humanize_number(base_bonus)}"
                if roll_perc > 0.95:
                    msg += _("{} had a surge of energy.\n").format(bold(user.display_name))
                    critlist.append(user)
                    crit_bonus = (random.randint(5, 20)) + (rebirths * 2)
                    crit_str = f"{self.emojis.crit}{humanize_number(crit_bonus)}"
                if c.hc is HeroClasses.wizard and c.heroclass["ability"]:
                    # wizard ability used
                    base_bonus = (random.randint(1, max(15, c.rebirths)) + 5) * (rebirths // 2)
                    base_str = f"{self.emojis.magic_crit}️{humanize_number(base_bonus)}"
                    if c.rebirths >= HC_VETERAN_RANK:
                        double_cast_bonus = round(0.65 * base_bonus)
                        base_str += f"+{self.emojis.magic_crit}️{humanize_number(double_cast_bonus)}"
                magic += int((roll + base_bonus + double_cast_bonus + crit_bonus + int_value) / mdef)
                bonus = base_str + crit_str
                report += (
                    f"{bold(user.display_name)}: "
                    f"{self.emojis.dice}({roll}) + "
                    f"{bonus} + "
                    f"{self.emojis.magic}{humanize_number(int_value)}\n"
                )
            else:
                magic += int((roll + int_value) / mdef) + c.rebirths // 5
                report += (
                    f"{bold(user.display_name)}: "
                    f"{self.emojis.dice}({roll}) + "
                    f"{self.emojis.magic}{humanize_number(int_value)}\n"
                )
            if session.insight[0] == 1 and user.id != session.insight[1].user.id:
                attack += int(session.insight[1].total_int * 0.2)
        if fumble_count == len(attack_list):
            report += _("No one!")
        msg += report + "\n"
        for user in fumblelist:
            if user in fight_list:
                if session.insight[0] == 1 and user.id != session.insight[1].user.id:
                    attack -= int(session.insight[1].total_att * 0.2)
                fight_list.remove(user)
            elif user in magic_list:
                if session.insight[0] == 1 and user.id != session.insight[1].user.id:
                    attack -= int(session.insight[1].total_int * 0.2)
                magic_list.remove(user)
        return (fight_list, magic_list, fumblelist, critlist, attack, magic, msg)

    async def handle_pray(self, guild_id, fumblelist, attack, diplomacy, magic):
        session = self._sessions[guild_id]
        ctx = session.ctx
        pray_list = list(set(session.pray + session.auto))  # add auto users to this list to check for clerics
        talk_list = list(set(session.talk))
        fight_list = list(set(session.fight))
        magic_list = list(set(session.magic))

        len_fight_list = len(fight_list)
        len_magic_list = len(magic_list)
        len_talk_list = len(talk_list)
        if len_fight_list >= len_magic_list and len_fight_list >= len_talk_list:
            fight_list += await self.filter_clerics_from_auto(ctx)
        elif len_magic_list > len_fight_list and len_magic_list >= len_talk_list:
            magic_list += await self.filter_clerics_from_auto(ctx)
        elif len_talk_list > len_fight_list and len_talk_list > len_magic_list:
            talk_list += await self.filter_clerics_from_auto(ctx)
        # get updated length
        len_fight_list = len(fight_list)
        len_talk_list = len(talk_list)
        len_magic_list = len(magic_list)

        god = await self.config.god_name()
        guild_god_name = await self.config.guild(self.bot.get_guild(guild_id)).god_name()
        if guild_god_name:
            god = guild_god_name
        msg = ""
        failed_emoji = self.emojis.fumble
        handled_pray_list = []
        for user in pray_list:
            try:
                c = await Character.from_json(ctx, self.config, user, self._daily_bonus)
            except Exception as exc:
                log.exception("Error with the new character sheet", exc_info=exc)
                continue

            if user in session.auto and c.hc is not HeroClasses.cleric:
                continue
            handled_pray_list.append(user)

            rebirths = c.rebirths * (2 if c.hc is HeroClasses.cleric else 1)
            if c.hc is HeroClasses.cleric:
                crit_mod = max(max(c.dex, c.luck // 2) + (c.total_int // 20), 0)
                mod = 0
                max_roll = 100 if c.rebirths >= 30 else 50 if c.rebirths >= 15 else 20
                if crit_mod != 0:
                    mod = round(crit_mod / 10)
                if c.rebirths < 15 < mod:
                    mod = 15
                    max_roll = 20
                elif (mod + 1) > 45:
                    mod = 45
                roll = max(random.randint((1 + mod), max_roll), 1)
                roll_perc = roll / max_roll
                vet_mod = 2 if c.rebirths >= HC_VETERAN_RANK else 0

                if len_fight_list + len_magic_list + len_talk_list == 0:
                    msg += _("{} blessed like a madman but nobody was there to receive it.\n").format(
                        bold(user.display_name)
                    )
                if roll_perc < 0.10:
                    pray_att_bonus = 0
                    pray_diplo_bonus = 0
                    pray_magic_bonus = 0
                    if fight_list:
                        pray_att_bonus = (5 * (len_fight_list + vet_mod)) - ((5 * (len_fight_list + vet_mod)) * max(rebirths * 0.01, 1.5))
                    if talk_list:
                        pray_diplo_bonus = (5 * (len_talk_list + vet_mod)) - ((5 * (len_talk_list + vet_mod)) * max(rebirths * 0.01, 1.5))
                    if magic_list:
                        pray_magic_bonus = (5 * (len_magic_list + vet_mod)) - ((5 * (len_magic_list + vet_mod)) * max(rebirths * 0.01, 1.5))
                    attack -= pray_att_bonus
                    diplomacy -= pray_diplo_bonus
                    magic -= pray_magic_bonus
                    fumblelist.append(user)
                    msg += _(
                        "{user}'s sermon offended the mighty {god}. {failed_emoji}"
                        "({len_f_list}{attack}/{len_t_list}{talk}/{len_m_list}{magic}) {roll_emoji}({roll})\n"
                    ).format(
                        user=bold(user.display_name),
                        god=god,
                        failed_emoji=failed_emoji,
                        attack=self.emojis.attack,
                        talk=self.emojis.talk,
                        magic=self.emojis.magic,
                        len_f_list=humanize_number(pray_att_bonus),
                        len_t_list=humanize_number(pray_diplo_bonus),
                        len_m_list=humanize_number(pray_magic_bonus),
                        roll_emoji=self.emojis.dice,
                        roll=roll,
                    )
                else:
                    mod = roll // 3 if not c.heroclass["ability"] else roll
                    pray_att_bonus = 0
                    pray_diplo_bonus = 0
                    pray_magic_bonus = 0

                    if fight_list:
                        pray_att_bonus = int(
                            (mod * (len_fight_list + vet_mod)) + ((mod * (len_fight_list + vet_mod)) * max(rebirths * 0.05, 1.5))
                        )
                    if talk_list:
                        pray_diplo_bonus = int(
                            (mod * (len_talk_list + vet_mod)) + ((mod * (len_talk_list + vet_mod)) * max(rebirths * 0.05, 1.5))
                        )
                    if magic_list:
                        pray_magic_bonus = int(
                            (mod * (len_magic_list + vet_mod)) + ((mod * (len_magic_list + vet_mod)) * max(rebirths * 0.05, 1.5))
                        )
                    attack += pray_att_bonus
                    magic += pray_magic_bonus
                    diplomacy += pray_diplo_bonus
                    if roll == 50:
                        roll_msg = _(
                            "{user} turned into an avatar of mighty {god}. "
                            "(+{len_f_list}{attack}/+{len_t_list}{talk}/+{len_m_list}{magic}) {roll_emoji}({roll})\n"
                        )
                    else:
                        roll_msg = _(
                            "{user} blessed you all in {god}'s name. "
                            "(+{len_f_list}{attack}/+{len_t_list}{talk}/+{len_m_list}{magic}) {roll_emoji}({roll})\n"
                        )
                    msg += roll_msg.format(
                        user=bold(user.display_name),
                        god=god,
                        attack=self.emojis.attack,
                        talk=self.emojis.talk,
                        magic=self.emojis.magic,
                        len_f_list=humanize_number(pray_att_bonus),
                        len_t_list=humanize_number(pray_diplo_bonus),
                        len_m_list=humanize_number(pray_magic_bonus),
                        roll_emoji=self.emojis.dice,
                        roll=roll,
                    )
            else:
                roll = random.randint(1, 10)
                if len_fight_list + len_talk_list + len_magic_list == 0:
                    msg += _("{} prayed like a madman but nobody else helped them.\n").format(bold(user.display_name))

                elif roll == 5:
                    attack_buff = 0
                    talk_buff = 0
                    magic_buff = 0
                    if fight_list:
                        attack_buff = 10 * (len_fight_list + rebirths // 15)
                    if talk_list:
                        talk_buff = 10 * (len_talk_list + rebirths // 15)
                    if magic_list:
                        magic_buff = 10 * (len_magic_list + rebirths // 15)

                    attack += attack_buff
                    magic += magic_buff
                    diplomacy += talk_buff
                    msg += _(
                        "{user}'s prayer called upon the mighty {god} to help you. "
                        "(+{len_f_list}{attack}/+{len_t_list}{talk}/+{len_m_list}{magic}) {roll_emoji}({roll})\n"
                    ).format(
                        user=bold(user.display_name),
                        god=god,
                        attack=self.emojis.attack,
                        talk=self.emojis.talk,
                        magic=self.emojis.magic,
                        len_f_list=humanize_number(attack_buff),
                        len_t_list=humanize_number(talk_buff),
                        len_m_list=humanize_number(magic_buff),
                        roll_emoji=self.emojis.dice,
                        roll=roll,
                    )
                else:
                    fumblelist.append(user)
                    msg += _("{}{}'s prayers went unanswered.\n").format(failed_emoji, bold(user.display_name))
        for user in fumblelist:
            if user in handled_pray_list:
                handled_pray_list.remove(user)
        return (handled_pray_list, fumblelist, attack, diplomacy, magic, msg)

    async def handle_talk(self, guild_id, fumblelist, critlist, diplomacy):
        session = self._sessions[guild_id]
        ctx = session.ctx
        cdef = max(session.monster_modified_stats["cdef"], 0.5)
        talk_list = list(set(session.talk))
        len_talk_list = len(talk_list)

        if len_talk_list > len(session.fight) and len_talk_list > len(session.magic):
            talk_list += await self.filter_clerics_from_auto(ctx)

        if len_talk_list >= 1:
            report = _("Talking Party: \n\n")
            msg = ""
            fumble_count = 0
        else:
            return (talk_list, fumblelist, critlist, diplomacy, "")

        failed_emoji = self.emojis.fumble
        for user in talk_list:
            try:
                c = await Character.from_json(ctx, self.config, user, self._daily_bonus)
            except Exception as exc:
                log.exception("Error with the new character sheet", exc_info=exc)
                continue
            crit_mod = max(max(c.dex, c.luck // 2) + (c.total_int // 50) + (c.total_cha // 20), 0)
            mod = 0
            max_roll = 100 if c.rebirths >= 30 else 50 if c.rebirths >= 15 else 20
            if crit_mod != 0:
                mod = round(crit_mod / 10)
            if c.rebirths < 15 < mod:
                mod = 15
            elif (mod + 1) > 45:
                mod = 45
            roll = max(random.randint((1 + mod), max_roll), 1)
            dipl_value = c.total_cha
            rebirths = c.rebirths * (3 if c.hc is HeroClasses.bard else 1)
            roll_perc = roll / max_roll
            if roll_perc < 0.10 or (roll + dipl_value) <= 0:
                if c.hc is HeroClasses.bard and c.heroclass["ability"]:
                    bonus = random.randint(5, max(15, c.rebirths))
                    dipl_bonus = int((roll - bonus + dipl_value + rebirths))
                    if c.rebirths >= HC_VETERAN_RANK:
                        dipl_bonus = int(0.01 * len(talk_list) * dipl_bonus)
                        msg += (_("{}'s music flows through the party. +{}{}\n")
                                .format(bold(user.display_name), self.emojis.talk, humanize_number(dipl_bonus)))
                    diplomacy += int(dipl_bonus / cdef)
                    report += f"{bold(user.display_name)} " f"🎲({roll}) +💥{bonus} +🗨{humanize_number(dipl_value)} | "
                else:
                    msg += _("{}{} accidentally offended the enemy.\n").format(failed_emoji, bold(user.display_name))
                    fumblelist.append(user)
                    fumble_count += 1
            elif roll_perc > 0.95 or c.hc is HeroClasses.bard:
                crit_str = ""
                crit_bonus = 0
                base_bonus = random.randint(5,  max(15, c.rebirths)) + rebirths
                if roll_perc > 0.95:
                    msg += _("{} made a compelling argument.\n").format(bold(user.display_name))
                    critlist.append(user)
                    crit_bonus = (random.randint(5, 20)) + (rebirths * 2)
                    crit_str = f"{self.emojis.crit} {crit_bonus}"

                dipl_bonus = 0
                if c.hc is HeroClasses.bard and c.heroclass["ability"]:
                    base_bonus = (random.randint(1, max(15, c.rebirths)) + 5) * (rebirths // 2)
                    if c.rebirths >= HC_VETERAN_RANK:
                        dipl_bonus = int(0.12 * len(talk_list) * base_bonus)
                        msg += (_("{}'s music rallied the party! +{}{}\n")
                                .format(bold(user.display_name), self.emojis.talk, humanize_number(dipl_bonus)))

                base_str = f"🎵 {humanize_number(base_bonus)}"
                diplomacy += int((roll + base_bonus + crit_bonus + dipl_value + dipl_bonus) / cdef)
                bonus = base_str + crit_str
                report += (
                    f"{bold(user.display_name)} "
                    f"{self.emojis.dice}({roll}) + "
                    f"{bonus} + "
                    f"{self.emojis.talk}{humanize_number(dipl_value)}\n"
                )
            else:
                diplomacy += int((roll + dipl_value + c.rebirths // 5) / cdef)
                report += (
                    f"{bold(user.display_name)} "
                    f"{self.emojis.dice}({roll}) + "
                    f"{self.emojis.talk}{humanize_number(dipl_value)}\n"
                )
            if session.insight[0] == 1 and user.id != session.insight[1].user.id:
                diplomacy += int(session.insight[1].total_cha * 0.2)
        if fumble_count == len(talk_list):
            report += _("No one!")
        msg = msg + report + "\n"
        for user in fumblelist:
            if user in talk_list:
                if session.insight[0] == 1 and user.id != session.insight[1].user.id:
                    diplomacy -= int(session.insight[1].total_cha * 0.2)
                talk_list.remove(user)
        return (talk_list, fumblelist, critlist, diplomacy, msg)

    async def handle_basilisk(self, ctx: commands.Context):
        session = self._sessions[ctx.guild.id]
        ctx = session.ctx
        fight_list = list(set(session.fight))
        talk_list = list(set(session.talk))
        pray_list = list(set(session.pray))
        magic_list = list(set(session.magic))
        auto_list = list(set(session.auto))
        participants = list(set(fight_list + talk_list + pray_list + magic_list + auto_list))
        if session.miniboss:
            failed = True
            req_item, slot = session.miniboss["requirements"]
            if req_item == "members":
                if len(participants) > int(slot):
                    failed = False
            elif req_item == "emoji" and session.reacted:
                failed = False
            else:
                for user in participants:  # check if any fighter has an equipped mirror shield to give them a chance.
                    try:
                        c = await Character.from_json(ctx, self.config, user, self._daily_bonus)
                    except Exception as exc:
                        log.exception("Error with the new character sheet", exc_info=exc)
                        continue
                    if any(x in c.sets for x in ["The Supreme One", "Ainz Ooal Gown"]):
                        failed = False
                        break
                    with contextlib.suppress(KeyError):
                        current_equipment = c.get_current_equipment()
                        for item in current_equipment:
                            item_name = str(item)
                            if item.rarity is not Rarities.forged and (
                                req_item in item_name or "shiny" in item_name.lower()
                            ):
                                failed = False
                                break
        else:
            failed = False
        return failed

    async def filter_clerics_from_auto(self, ctx):
        session = self._sessions[ctx.guild.id]
        results = []
        for user in session.auto:
            try:
                c = await Character.from_json(ctx, self.config, user, self._daily_bonus)
            except Exception as exc:
                log.exception("Error with the new character sheet", exc_info=exc)
                continue
            if c.hc is not HeroClasses.cleric:
                results.append(user)
        return results

    async def _add_rewards(
        self, ctx: commands.Context, user: Union[discord.Member, discord.User], exp: int, cp: int, special: Treasure
    ) -> Optional[str]:
        async with self.get_lock(user):
            try:
                c = await Character.from_json(ctx, self.config, user, self._daily_bonus)
            except Exception as exc:
                log.exception("Error with the new character sheet", exc_info=exc)
                return
            rebirth_text = ""
            c.exp += exp
            member = ctx.guild.get_member(user.id)
            cp = max(cp, 0)
            if cp > 0:
                try:
                    await bank.deposit_credits(member, cp)
                except BalanceTooHigh as e:
                    await bank.set_balance(member, e.max_balance)
            extra = ""
            rebirthextra = ""
            lvl_start = c.lvl
            lvl_end = int(max(c.exp, 0) ** (1 / 3.5))
            lvl_end = lvl_end if lvl_end < c.maxlevel else c.maxlevel
            levelup_emoji = self.emojis.level_up
            rebirth_emoji = self.emojis.rebirth
            if lvl_end >= c.maxlevel:
                rebirthextra = _("{} You can now rebirth {}").format(rebirth_emoji, user.mention)
            if lvl_start < lvl_end:
                # recalculate free skillpoint pool based on new level and already spent points.
                c.lvl = lvl_end
                assigned_stats = c.skill["att"] + c.skill["cha"] + c.skill["int"]
                starting_points = await calculate_sp(lvl_start, c) + assigned_stats
                ending_points = await calculate_sp(lvl_end, c) + assigned_stats

                if c.skill["pool"] < 0:
                    c.skill["pool"] = 0
                c.skill["pool"] += ending_points - starting_points
                if c.skill["pool"] > 0:
                    extra = _(" You have {} skill points available.").format(bold(str(c.skill["pool"])))
                rebirth_text = _("{} {} is now level {}!{}\n{}").format(
                    levelup_emoji, user.mention, bold(str(lvl_end)), extra, rebirthextra
                )
            if c.rebirths > 1:
                roll = random.randint(1, 100)
                if lvl_end == c.maxlevel:
                    roll += random.randint(50, 100)
                if not special:
                    special = Treasure()
                    if c.rebirths > 1 and roll < 50:
                        special.normal += 1
                    if c.rebirths > 5 and roll < 30:
                        special.rare += 1
                    if c.rebirths > 10 > roll:
                        special.epic += 1
                    if c.rebirths > 15 and roll < 5:
                        special.legendary += 1
                    # if special == [0, 0, 0, 0, 0, 0]:
                    # special = False
                else:
                    if c.rebirths > 1 and roll < 50:
                        special.normal += 1
                    if c.rebirths > 5 and roll < 30:
                        special.rare += 1
                    if c.rebirths > 10 > roll:
                        special.epic += 1
                    if c.rebirths > 15 and roll < 5:
                        special.legendary += 1
            if special:
                c.treasure += special
            await self.config.user(user).set(await c.to_json(ctx, self.config))
            return rebirth_text

    async def _adv_countdown(self, ctx: commands.Context, seconds, title) -> asyncio.Task:
        await self._data_check(ctx)

        async def adv_countdown():
            secondint = int(seconds)
            adv_end = await _get_epoch(secondint)
            timer, done, sremain = await _remaining(adv_end)
            timer = f"<t:{int(adv_end)}:R>"
            message_adv = await ctx.send(f"⏳ [{title}] {timer}")
            deleted = False
            while not done:
                timer, done, sremain = await _remaining(adv_end)
                self._adventure_countdown[ctx.guild.id] = (timer, done, sremain)
                if done:
                    if not deleted:
                        await message_adv.delete()
                    break
                await asyncio.sleep(1)
            log.debug("Timer countdown done.")

        return ctx.bot.loop.create_task(adv_countdown())

    async def _data_check(self, ctx: commands.Context):
        try:
            self._adventure_countdown[ctx.guild.id]
        except KeyError:
            self._adventure_countdown[ctx.guild.id] = 0
        try:
            self._rewards[ctx.author.id]
        except KeyError:
            self._rewards[ctx.author.id] = {}
        try:
            self._trader_countdown[ctx.guild.id]
        except KeyError:
            self._trader_countdown[ctx.guild.id] = 0

    @commands.Cog.listener()
    async def on_message_without_command(self, message):
        await self._ready_event.wait()
        if self.red_340_or_newer:
            if message.guild is not None:
                if await self.bot.cog_disabled_in_guild(self, message.guild):
                    return
            else:
                return
        channels = await self.config.guild(message.guild).cart_channels()
        if not channels:
            return
        if message.channel.id not in channels:
            return
        if not message.author.bot and message.guild.id not in self._sessions:
            roll = random.randint(1, 20)
            if roll == 20:
                try:
                    self._last_trade[message.guild.id]
                except KeyError:
                    self._last_trade[message.guild.id] = 0
                ctx = await self.bot.get_context(message)
                ctx.command = self.makecart
                await asyncio.sleep(5)
                timeout = await self.config.guild(ctx.guild).cart_timeout()
                trader = Trader(timeout, ctx, self)
                await trader.start(ctx)
                await asyncio.sleep(timeout)
                trader.stop()
                await trader.on_timeout()

    async def _roll_chest(self, chest_type: Rarities, c: Character) -> Item:
        # set rarity to chest by default
        rarity = chest_type
        if chest_type is Rarities.pet:
            rarity = Rarities.normal
        INITIAL_MAX_ROLL = 400
        # max luck for best chest odds
        MAX_CHEST_LUCK = 200
        # lower gives you better chances for better items
        max_roll = INITIAL_MAX_ROLL - round(c.luck) - (c.rebirths // 2)
        top_range = max(max_roll, INITIAL_MAX_ROLL - MAX_CHEST_LUCK)
        roll = max(random.randint(1, top_range), 1)
        if chest_type is Rarities.normal:
            if roll <= INITIAL_MAX_ROLL * 0.05:  # 5% to roll rare
                rarity = Rarities.rare
            else:
                pass  # 95% to roll common
        elif chest_type is Rarities.rare:
            if roll <= INITIAL_MAX_ROLL * 0.05:  # 5% to roll epic
                rarity = Rarities.epic
            elif roll <= INITIAL_MAX_ROLL * 0.95:  # 90% to roll rare
                pass
            else:
                rarity = Rarities.normal  # 5% to roll normal
        elif chest_type is Rarities.epic:
            if roll <= INITIAL_MAX_ROLL * 0.05:  # 5% to roll legendary
                rarity = Rarities.legendary
            elif roll <= INITIAL_MAX_ROLL * 0.90:  # 85% to roll epic
                pass
            else:  # 10% to roll rare
                rarity = Rarities.rare
        elif chest_type is Rarities.legendary:
            if roll <= INITIAL_MAX_ROLL * 0.75:  # 75% to roll legendary
                pass
            elif roll <= INITIAL_MAX_ROLL * 0.95:  # 20% to roll epic
                rarity = Rarities.epic
            else:
                rarity = Rarities.rare  # 5% to roll rare
        elif chest_type is Rarities.ascended:
            if roll <= INITIAL_MAX_ROLL * 0.55:  # 55% to roll set
                rarity = Rarities.ascended
            else:
                rarity = Rarities.legendary  # 45% to roll legendary
        elif chest_type is Rarities.pet:
            if roll <= INITIAL_MAX_ROLL * 0.02:  # 2% to roll ascended
                rarity = Rarities.ascended
            elif roll <= INITIAL_MAX_ROLL * 0.17:  # 15% to roll legendary
                rarity = Rarities.legendary
            elif roll <= INITIAL_MAX_ROLL * 0.52:  # 35% to roll epic
                rarity = Rarities.epic
            elif roll <= INITIAL_MAX_ROLL * 0.87:  # 35% to roll rare
                rarity = Rarities.rare
            else:
                rarity = Rarities.normal  # 13% to roll common
        # if chest_type is set, rarity is already set

        return await self._genitem(c._ctx, rarity)

    def format_auto_user_name(self, ctx, user):
        session = self._sessions.get(ctx.guild.id)
        if user in session.auto:
            return "{} {}".format(user.mention, self.emojis.auto)
        else:
            return user.mention

    async def _reward(self, ctx: commands.Context, userlist, amount: int, modif: float, special: Treasure) -> str:
        """
        text += await self._reward(
                    ctx,
                    [u for u in talk_list + pray_list if u not in fumblelist],
                    amount,
                    round((diplomacy / dipl) * 0.25),
                    treasure,
                )
        """
        daymult = self._daily_bonus.get(str(datetime.today().isoweekday()), 0)
        xp = max(1, round(amount))
        cp = max(1, round(amount))
        newxp = 0
        newcp = 0
        rewards_list = []
        phrase = ""
        reward_message = ""
        currency_name = await bank.get_currency_name(
            ctx.guild,
        )
        can_embed = not ctx.guild or (await _config.guild(ctx.guild).embed() and await ctx.embed_requested())
        session = self._sessions.get(ctx.guild.id)
        if session:
            session_bonus = 0 if session.easy_mode else 1
        else:
            session_bonus = 0
        async for user in AsyncIter(userlist, steps=100):
            self._rewards[user.id] = {}
            try:
                c = await Character.from_json(ctx, self.config, user, self._daily_bonus)
            except Exception as exc:
                log.exception("Error with the new character sheet", exc_info=exc)
                continue

            userxp = round(0.75 * int(xp + (xp * 0.5 * c.rebirths) + max((xp * 0.1 * min(250, c.total_stats / 50)), 0)))
            usercp = round(0.75 * int(cp + max((cp * 0.1 * min(1000, c.total_stats / 35)), 0)))

            base_userxp = userxp
            base_usercp = usercp
            userxp = int(base_userxp * (c.gear_set_bonus.get("xpmult", 1) + daymult + session_bonus))
            usercp = int(base_usercp * (c.gear_set_bonus.get("cpmult", 1) + daymult))

            if user in session.auto:
                userxp = userxp // 2
                usercp = usercp // 2
            newxp += userxp
            newcp += usercp

            # bonus roll for pets - 45% base chance to proc
            roll = random.randint(1, 100)
            target_number = 45
            if c.heroclass.get("pet", {}).get("bonuses", {}).get("always", False):
                roll = 1  # pick 1 to guarantee bonus if pet allows it
            if roll < target_number and c.heroclass["pet"]:
                petxp = int(base_userxp * (c.heroclass["pet"]["bonus"] - 1))
                petcp = int(base_usercp * (c.heroclass["pet"]["bonus"] - 1))

                if user in session.auto:
                    petxp = petxp // 2
                    petcp = petcp // 2
                newxp += petxp
                userxp += petxp
                self._rewards[user.id]["xp"] = userxp
                newcp += petcp
                usercp += petcp
                self._rewards[user.id]["cp"] = usercp
                reward_message += "{mention} gained {xp} XP and {coin} {currency}.\n".format(
                    mention=self.format_auto_user_name(ctx, user) if can_embed else f"{bold(user.display_name)}",
                    xp=humanize_number(int(userxp)),
                    coin=humanize_number(int(usercp)),
                    currency=currency_name,
                )
                percent = round((c.heroclass["pet"]["bonus"] - 1.0) * 100)
                phrase += _("\n{user} received a {percent}% reward bonus from their {pet_name}.").format(
                    user=bold(user.display_name),
                    percent=bold(str(percent)),
                    pet_name=c.heroclass["pet"]["name"],
                )

            else:
                reward_message += "{mention} gained {xp} XP and {coin} {currency}.\n".format(
                    mention=self.format_auto_user_name(ctx, user),
                    xp=humanize_number(int(userxp)),
                    coin=humanize_number(int(usercp)),
                    currency=currency_name,
                )
                self._rewards[user.id]["xp"] = userxp
                self._rewards[user.id]["cp"] = usercp
            if special:
                self._rewards[user.id]["special"] = special
            else:
                self._rewards[user.id]["special"] = False
            rewards_list.append(f"{bold(user.display_name)}")

        self._reward_message[ctx.message.id] = reward_message
        to_reward = " and ".join(
            [", ".join(rewards_list[:-1]), rewards_list[-1]] if len(rewards_list) > 2 else rewards_list
        )

        word = "has" if len(userlist) == 1 else "have"
        if special:
            chest_str = special.get_ansi()
            chest_type = box(_("{chest_str} treasure chest!").format(chest_str=chest_str), lang="ansi")
            phrase += _(
                "\n{b_reward} {word} been awarded {xp} xp and found "
                "{cp} {currency_name} (split based on stats). "
                "You also secured {chest_type}"
            ).format(
                b_reward=to_reward,
                word=word,
                xp=humanize_number(int(newxp)),
                cp=humanize_number(int(newcp)),
                currency_name=currency_name,
                chest_type=chest_type,
            )
        else:
            phrase += _(
                "\n{b_reward} {word} been awarded {xp} xp and found {cp} {currency_name} (split based on stats)."
            ).format(
                b_reward=to_reward,
                word=word,
                xp=humanize_number(int(newxp)),
                cp=humanize_number(int(newcp)),
                currency_name=currency_name,
            )
        return phrase

    def cog_unload(self):
        if self.cleanup_loop:
            self.cleanup_loop.cancel()
        if self._init_task:
            self._init_task.cancel()
        if self.gb_task:
            self.gb_task.cancel()

        for msg_id, task in self.tasks.items():
            task.cancel()

        for lock in self.locks.values():
            with contextlib.suppress(Exception):
                lock.release()
