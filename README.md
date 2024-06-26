# Adventure

In this RPG cog originally by locastan - TrustyJAID, Draper, and myself have crafted a fun idle game you can play with the members of your servers.

### >>> This branch is compatible with Red 3.5, and not 3.4.x <<<

If you need a Red 3.4 version of this cog, see [here](https://github.com/aikaterna/gobcog/tree/red3.4).


## Basic Usage

`[p]` in this readme represents your bot's command prefix. Whenever you see a command in this guide, you can receive more detailed help by using `[p]help` with the command name.

To start an adventure, use `[p]adventure` or `[p]a`. Reactions will appear underneath the text of the adventure randomly selected for your group. Use 🗡 to attack the monster, ✨ to use magic on the monster, 🗨 to talk with the monster, 🛐 to pray to the god Herbert (customizable). The more people helping the easier it is to defeat the monster and acquire its loot. 

## Auto Battle
After taking an action in the battle, each user who manually participated will be placed on the auto-battle list.  

These auto players will help participate in the next set number of fights based on the highest count action taken.  
If the number of players Attacking plus the number of players Casting add up to be higher than Talking, then auto players will 
fight based on the preference set by `[p]auto mode`.  
If the number of players Talking is higher than the number of players Attacking and Casting, then auto players
will talk regardless of their auto mode.  
If the number of Attackers plus Casters is equal to Talkers, then fighting will take higher priority.

Clerics are an exception to this rule - they will always perform the Pray action, and non-Clerics will never Pray.  

Auto-battlers will gain 50% of the experience and gold from the encounter, but will receive the full amount of treasure.  

After 20 auto-battles without any manual action, the user will no longer participate in the battle automatically.  
Every time a user takes a manual option (i.e. pressing Attack, Magic, Talk, or Pray again), they will have their auto-battle count reset.  
A user can also manually remove themselves from the Auto list by clicking on the Auto action button and confirming to Run.

Auto-battle mode can be toggled on/off using the `[p]auto` command or toggle in `[p]ibackpack`.

## Hero/Heroclass

Classes can be chosen at level 10 by using `[p]heroclass`. Available classes are Tinkerer, Berserker, Wizard, Cleric, Ranger and Bard.  
At rebirth level 20, each heroclass unlocks their Veteran rank, and the Pyschic heroclass is unlocked (more on the rebirthing system below).

Main Stats: Attack (ATT/ATK), Charisma/Diplomacy (CHA/DIPL), Intelligence (INT)  
Minor Stats: Dexterity (DEX), Luck (LUCK/LUK)  
  
While each class has a main stat that benefits them more than others, Dexterity and Luck benefit every class. Dexterity can lessen your repair bills after a failed adventure and help your hero get critical hits, while luck can benefit the outcome of special attacks, reduce cooldown times, augment critical strikes, affect loot chest outcomes, and reduce the price of items.  
  
**Tinkerers** can forge two different items into a device bound to their very soul.  
Special ability: Use the `[p]forge` command.  
* Forge together two items in your backpack to potentially make an incredibly powerful random item.  
Preferred stat: INT or ATK  
Higher rebirth levels allow access to better forging materials.
* **Veteran Tinkerers** can forge using Ascended materials.
  
**Berserkers** have the option to rage and add big bonuses to attacks, but fumbles hurt.  
Use the `[p]rage` command when attacking in an adventure.  
* Causes a large amount of ATK-based/Physical-based damage.  
Preferred stat: ATK  
Rebirths provide not only a base bonus to attacks as Berserkers grow stronger, but they augment critical strike chance and attack value.  
* **Veteran Berserkers**' rage bonus attack will pierce the enemy, ignoring any physical defense.
  
**Clerics** can bless the entire group when praying.  
Use the `[p]bless` command when fighting in an adventure.  
* Bless your groups' damage by invoking your deity. The more people that are participating, the harder the deity smites their foes... if they choose to help.  
Preferred stat: INT  
Every 15 rebirths a Cleric recieves another +1 to their successful prayer damage multiplier.  
* **Veteran Clerics** have an addition +2 count to each action list (e.g. Fight, Magic, Talk), provided at least 1 person has taken that action.
  
**Rangers** can fire a volley of arrows at the enemy, but not every hit will land.  
Use the `[p]rain` command when attacking in an adventure.    
* Rangers also have a special bond with their pets, enhancing the Ranger's abilities in combat.  
Preferred stat: ATT 
* **Veteran Rangers**'s rain will fire more arrows in their volley that will hit for more damage.

**Wizards** have the option to focus and add large bonuses to their magic, but their focus can sometimes go astray...  
Use the `[p]focus` command when attacking in an adventure.  
* Causes a large amount of Int-based/Magic-based damage.  
Preferred stat: INT  
Rebirths provides bonuses to the Wizard's focus abilities.  
* **Veteran Wizards** have the ability to double cast their focus spells. The second cast has slightly less effectiveness than the first cast.

**Bards** can perform to aid their comrades in diplomacy.  
Use the `[p]music` command when being diplomatic in an adventure.  
* High bonus to diplomatic actions. 
Preferred stat: CHA  
Rebirth levels can buff the base value of the bard's diplomacy.  
* **Veteran Bards** provide party wide bonus to diplomacy based on their own musical bonus.

**Psychics** can show the enemy's weaknesses to their group allowing them to target the monster's weak-points.  
Use the `[p]insight` command in an adventure. 
* A successful insight into an enemy's weak points during an adventure can turn the tide on difficult encounters.  
Preferred stat: INT  
* This prestige class unlocks at rebirth 20, so it does not have a Veteran rank.

## Pet
* A hero can gain a pet as a companion, which can find items and give reward bonuses. Raise your CHA stats to catch better pets!
* Use the `[p]pet` command to try to catch a pet companion. Pet catching can be spammy, so `[p]pet` can be run in DMs.  
`[p]pet forage` sends a pet to search for items, and `[p]pet free` will free your companion in case you wish to try your hand at capturing something that brings in more gold and loot from fights.
* Catch one of over 300 randomly-generated pets in search of the legendary beasts rumored to exist...

## Basic Commands for Players

`[p]adventure` or `[p]a`
* Start an adventure

`[p]stats`
* See your stats, or the stats of another user.

`[p]backpack`
* Check the backpack. Use `[p]ebackpack` to only show items that you can equip at that time. Use `[p]cbackpack` for complex argparse-based backpack management - see `[p]help cbackpack` to see how to use this command.
* Use `[p]help backpack` to see a list of useful backpack management subcommands, including player item trading.

`[p]ibackpack`
* An interactive backpack tool to filter, sell items, and open loot. Provides most of the basic functionality you would normally use, but more advance users can still use some of the richer functionality of `[p]backpack` and `[p]cbackpack`.

`[p]equip` / `[p]unequip`
* Equip/Unequip items by using the item name with the command

`[p]negaverse` or `[p]nv`
* Try your luck in combat vs. a shadowy apparition from the void for a chance at XP... or a chance of your items and gold being taken from you instead.

`[p]negaverse_percent` or `[p]nv%`
* Same command as `[p]negaverse` but takes an integer as a percentage of your current bank balance to send as the offering.

`[p]loot`
* Shows the count of your precious loot chests. From there, multiple chests of the same type can be opened at once, e.g. `[p]loot epic 5` will loot 5 epic chests at once and display the contents. Opening loot chests one by one will display a comparison to what the hero has equipped at that point in time.

`[p]convert`
* Available after Rebirth level 2
* Convert 25 loot chests to the next highest rarity. Only available up to Legendary.

`[p]rebirth`
* Players progress through a rebirth prestige leveling system alongside regular player levels. For every rebirth, the level cap is increased. Players will need to watch their level cap on the `[p]stats` output and rebirth when needed - hitting level cap during an adventure will also alert the player at the end during the loot recap.
* On a rebirth, a server admin or bot-owner settable percentage of gold is taken from the player (default at 90%).
* Legendary and Ascended items have a quality called Durability/Degrade Level (DEG) that is reduced by 1 every time a rebirth occurs. When this number hits 0, they are destroyed on rebirth.
* Set items never degrade.
* Normal, rare, and epic items are destroyed by the chaotic powers of rebirth.
* In return, rebirthing gives higher base stats and a higher max level, an adventure dice increase at rebirth 15 and 30, and the ability to have a clearer picture of incoming monsters during Hard Mode adventures.

`[p]skill`
* When players level, they acquire skill points that they can use in improving one of the main stats (ATK, CHA, INT). These numbers are reset on a rebirth, but as players level in the rebirth level system, they will keep an increasingly larger amount of the base when they rebirth again.

`[p]auto`
* Use this to turn auto battling `on` or `off`. While `off`, you will not engage in any upcoming adventures automatically even if you manually join the fight.  
When turning from `off` to `on` again, you must currently be in combat or enter combat manually to get back onto the auto list.
* Use `p[auto] mode attack` to set your fight preference to attack or `p[auto] mode magic` to set it to cast.  
If you don't set anything, you will fight based on your the higher stat between ATT and INT. If both are equal, ATT wins.

## More Advanced Commands for Players

`[p]backpack disassemble`
* Take apart an unused piece of gear to try to get something good out of it. This complex command also uses the same argparse-style command structure that `[p]cbackpack` does - I recommend reading https://github.com/aikaterna/gobcog/blob/master/docs/cbackpack.md for more information.


## Monsters, Adventures, and the Numbers

When an adventure is over, an output of the outcome is displayed. Sometimes the numbers won't seem to match up - why did that owlspider resist your 1,000 magic damage that you threw at it - and the output says 680 damage instead? Each monster has a resistance table where they could be resistant to magic like in this example, and it mitigated a good chunk of the attack. Having a balanced group across all classes is where adventure really shines - physical and magical damage is combined in adventures, and charisma stands alone in its persuading power to turn the fight around without fighting. Successful prayers by clerics over large groups augment damage of both damage types. If a group defeats an adventure on "both sides" of the damage (both physical+magical and diplomacy) the rewards are greater for the whole group.


## Items

Items can be looted from loot chests received from a successful adventure or bought from a Trader Cart that appears in chat. 

Going from least to most powerful, generally the progression is normal < rare < epic < Legendary < Ascended < Set.
Forged items are a Tinker's specialty.
Event items can be created by a bot owner as a special reward to hand out to specific users for bot events or other incentive-based rewards.

```ansi
{Event:''Event items look like this''}
{.:'Forged items look like this':.}
{Set:''Set items look like this''}
{Ascended:''Ascended items look like this''}
{Legendary:'Legendary items look like this'}
[epic items look like this]
.rare_items_look_like_this
normal items look like this
```

`[p]setinfo` displays information about gear sets and their bonuses.

Set items have a stacking set bonus. For example, if one set has 9 pieces, and `[p]setinfo` shows that it has a bonus at 3 pieces equipped, 6 pieces equipped, and 9 pieces equipped, all three of those bonuses will be applied if the player has all 9 pieces equipped.


## Advanced Adventure for Admins/Bot Owners

Read `[p]adventureset` and familiarize yourself with the subcommands available in that command. A few of the commands are highlighted below as they offer options that affect the whole game and also the bot itself.

The bot owner can spawn specific adventure monsters that are in the theme list by using `[p]adventure` with the name of the monster.

### Easy Mode vs Hard Mode
`[p]adventureset easymode`

* Users gain more XP per adventure if Hard Mode is used
* Hard Mode randomly obscures details about the monster the group is fighting
* The Psychic prestige heroclass is intended to be leveraged against Hard Mode by revealing critical details about how to defeat the monster

### Daily bonuses
`[p]adventureset dailybonus`

Certain days of the week receive certain bonuses for XP and gold which is configurable.

### Adventure Gold vs. Red Economy credits
`[p]adventureset sepcurrency`

Adventure gold is the default currency of adventure, which is separate from Red credits. This gold currency can provide an opportunity for users to have fun collecting it aside from Red credits in other games or cogs. Cogs can be written to leverage adventure gold, so there are infinite possibilities on how to best use this extra currency for your bot. If you want a unified currency, or if you aren't interested in another currency for your users, it can be toggled off.

Adventure is a global (bot-wide) game in the idea that users use the same character across all servers the bot can see, but there are some things that provide different outcomes based on whether the bot is set to a global or server-based economy. For example with rebirth cost, if the Red bank/economy is in server-based mode, each server will be able to set their rebirth cost while if it is in global mode, only the bot owner will be able to use the command. In server-based mode, authorized users have either a bot Admin role (check `[p]set showsettings` to display Admin roles on Red), or they have the Manage Guild permission.

### Make Your Own Adventure Theme
`[p]adventureset theme`

Copy the default folder in `<datapath>/cogs/CogManager/adventure/data/` to the cog's data directory in `<datapath>/cogs/Adventure/` and name it a one word folder name. Make your changes to the files while making sure to validate them with a site like <https://jsonformatter.curiousconcept.com/>. Load your new theme with `[p]adventureset theme <folder_name>`.

### The Trader Cart System
`[p]adventureset cart <#channel>`

Sometimes a traveling merchant cart will roll past offering new items for adventurers to buy or loot chests to purchase. Admins/Bot owners must set this cart channel first before carts will appear. Carts have roughly a 3h return time, but this is also configurable.

### Adventure Alerts

If you want your users to be able to sign up for pings when specific monster types/potential boss monsters appear, install `adventurealert` by TrustyJAID (https://github.com/TrustyJAID/Trusty-cogs).
