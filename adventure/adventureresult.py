import logging
from typing import Dict, List, MutableMapping, TypedDict

import discord
from redbot.core import commands

log = logging.getLogger("red.cogs.adventure")


class StatRange(TypedDict):
    stat_type: str
    min_stat: float
    max_stat: float
    average_talk: float
    average_attack: float
    win_percent: float


class Raid(TypedDict):
    main_action: str
    amount: float
    num_ppl: int
    success: bool
    auto_users: Dict[discord.Member, int]


class AdventureResults:
    """Object to store recent adventure results."""

    def __init__(self, num_raids: int):
        self._num_raids: int = num_raids
        self._last_raids: MutableMapping[int, List[Raid]] = {}

    def add_result(self, ctx: commands.Context, main_action: str, amount: float, num_ppl: int, success: bool,
                   manual_users: List[discord.Member], auto_users: List[discord.Member], exclusion_users: List):
        """Add result to this object.
        :main_action: Main damage action taken by the adventurers
            (highest amount dealt). Should be either "attack" or
            "talk". Running will just be notated by a 0 amount.
        :amount: Amount dealt.
        :num_ppl: Number of people in adventure.
        :success: Whether adventure was successful or not.
        :manual_users: List of users who have taken a manual action this turn - will be added to auto if not excluded.
        :auto_users: List of users who should is currently taking auto actions.
        :exclusion_users: List of users who should be excluded from auto list.
        """
        if ctx.guild.id not in self._last_raids:
            self._last_raids[ctx.guild.id] = []

        if len(self._last_raids.get(ctx.guild.id, [])) >= self._num_raids:
            try:
                self._last_raids[ctx.guild.id].pop(0)
            except IndexError:
                pass

        # add manual users to the next auto list
        saved_auto_users = {}
        for user in manual_users:
            saved_auto_users[user] = self._num_raids * 2
        # auto users can only be added back in if they have been in here for less than num_raids
        raids = self._last_raids.get(ctx.guild.id, [])
        if len(raids) > 0:
            raid = raids[-1]
            for user in auto_users:
                if user not in raid["auto_users"]:
                    # if the user wasn't on the previous auto list, reset them
                    count = self._num_raids * 2
                    saved_auto_users[user] = count
                else:
                    count = raid["auto_users"][user]
                if count == 0:
                    # no more auto for this user
                    continue
                else:
                    saved_auto_users[user] = count - 1
        else:
            for user in auto_users:
                count = self._num_raids * 2
                saved_auto_users[user] = count - 1

        for user in exclusion_users:
            saved_auto_users.pop(user, None)

        self._last_raids[ctx.guild.id].append(
            Raid(main_action=main_action, amount=amount, num_ppl=num_ppl, success=success, auto_users=saved_auto_users)
        )

    def get_last_auto_users(self, ctx: commands.Context):
        raids = self._last_raids.get(ctx.guild.id, [])
        if len(raids) > 0:
            return list(raids[-1]["auto_users"].keys())
        else:
            return []

    def get_stat_range(self, ctx: commands.Context) -> StatRange:
        """Return reasonable stat range for monster pool to have based
        on last few raids' damage.

        :returns: Dict with stat_type, min_stat and max_stat.
        """
        # how much % to increase damage for solo raiders so that they
        # can't just solo every monster based on their own average
        # damage
        if ctx.guild.id not in self._last_raids:
            self._last_raids[ctx.guild.id] = []
        SOLO_RAID_SCALE: float = 0.25
        min_stat: float = 200.0
        max_stat: float = 600.0
        stat_type: str = "hp"
        win_percent: float = 0.5
        if len(self._last_raids.get(ctx.guild.id, [])) == 0:
            return StatRange(stat_type=stat_type, min_stat=min_stat, max_stat=max_stat, win_percent=win_percent,
                             average_talk=0, average_attack=0)

        # tally up stats for raids
        num_attack = 0
        average_attack = 0
        attack_amount = 0
        num_talk = 0
        average_talk = 0
        talk_amount = 0
        num_wins = 0
        stat_type = "hp"
        avg_amount = 0
        raids = self._last_raids.get(ctx.guild.id, [])
        raid_count = len(raids)
        if raid_count == 0:
            win_percent = 0.0
        else:
            for raid in raids:
                if raid["main_action"] == "attack":
                    num_attack += 1
                    attack_amount += raid["amount"]
                    if raid["num_ppl"] == 1:
                        attack_amount += raid["amount"] * SOLO_RAID_SCALE
                else:
                    num_talk += 1
                    talk_amount += raid["amount"]
                    if raid["num_ppl"] == 1:
                        talk_amount += raid["amount"] * SOLO_RAID_SCALE
                if raid["success"]:
                    num_wins += 1
            average_talk = talk_amount / num_talk if num_talk > 0 else 0
            average_attack = attack_amount / num_attack if num_attack > 0 else 0
            if num_attack > 0:
                avg_amount = average_attack
            if attack_amount < talk_amount:
                stat_type = "dipl"
                avg_amount = average_talk
            win_percent = num_wins / raid_count
            min_stat = avg_amount * 0.5
            max_stat = avg_amount * 2
            # want win % to be at least 50%, even when solo
            # if win % is below 50%, scale back min/max for easier mons
            if win_percent < 0.5:
                min_stat = avg_amount * win_percent
                max_stat = avg_amount * 1.5
        return StatRange(stat_type=stat_type, min_stat=min_stat, max_stat=max_stat, win_percent=win_percent,
                         average_talk=average_talk, average_attack=average_attack)

    def __str__(self):
        return str(self._last_raids)
