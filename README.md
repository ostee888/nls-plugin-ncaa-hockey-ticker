# NCAA Hockey Ticker Plugin
 
## Table of Contents

- [Installing the Plugin](#installing-the-plugin)
- [Setting Your Team(s) To Display](#Setting-Your-Team(s)-to-Display)


## Installing The Plugin

To install the plugin onto the NHL-LED-SCOREBOARD, log into your NLS Control Hub (IP ADDRESS:8000), and go to the plugins tab. Copy the link "https://github.com/ostee888/nls-plugin-ncaa-hockey-ticker" and paste it into the URL section. Then press Add Plugin. 


### Setting Your Team(s) to Display

### 1) Getting The Name
This plugin allows for one or multiple teams to be displayed on the scoreboard. To add teams you must look up their NCAA website name. This can be done by looking on the Scores or Rankings page and copying the name. https://www.ncaa.com/scoreboard/icehockey-men/d1

__Example:__
```
Michigan State = Michigan St.
Saint Thomas = St. Thomas (MN)
```

### 2) Add Names to the Config.json

In the terminal, navigate to the plugins folder. From the nhl-led-scoreboard directory run:
```
cd src/boards/plugins/ncaa-hockey-ticker
```

Modify the teams array with the name(s) you want to display.

__Single Team__

config.json
```json
{
  "teams": ["Michigan Tech"],
  "lookahead_days": 6,
  "display_seconds": 8
}
```
__Multiple Teams__

config.json
```json
{
  "teams": ["Michigan Tech","Quinnipiac","Michigan","St. Thomas (MN)"],
  "lookahead_days": 6,
  "display_seconds": 8
}
```
Other options in the config.json include the days into the future the board looks for new games. Display seconds is the time each board is displayed (per team).



### Layout Options

The layout_128x64.json includes the locations of all the text elements along with the size of the images.

The size of the logos for the teams can be modified by changing the "width" and "height".
```json
"ncaa_scoreboard": {
    "logo_size": {
      "width": 76,
      "height": 76
    }
```

The rest of the elements X and Y coordinates can be adjusted to make everything look the way you want. All coordinates reference the horizontal and vertical CENTER of the object.
