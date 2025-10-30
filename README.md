# Twitch Auto Category Manager - OBS Plugin

Automatically updates your Twitch stream category based on running applications.  
Supports custom game mappings and the Discord detectable apps database as a fallback.

---

## Features

- **Automatic Twitch category updates** based on the active application.
- **Custom game mappings** with configurable priority.
- **Discord detectable apps** integration for fallback detection.
- **OBS integration**: add mappings and refresh the database directly from the OBS UI.
- **OAuth2 authentication with Twitch** (login via browser).
- Fully open-source under **GPLv3**.

---

## Installation

1. Download TwitchAutoCategory - DiscordDB Implementation.py from either this repository or from OBS forums.
2. Copy the plugin file to your OBS scripts folder. This is found in C > Program Files > obs-studio > data > obs-plugins > frontend-tools > scripts.
   Also copy pasting this in a run window opens the same folder (Win + R)
   ```json
   C:\Program Files\obs-studio\data\obs-plugins\frontend-tools\scripts
4. Paste the file in.

5. Navigate to `Tools -> Scripts`

   <img width="199" height="239" alt="image" src="https://github.com/user-attachments/assets/0bdb9017-ae04-45ff-a0a4-cbe2e11a3553" />

7. Add the script to OBS by clicking the `+` icon

   <img width="1292" height="636" alt="image" src="https://github.com/user-attachments/assets/09cf5b74-c2c4-48f1-a3ac-15db5a215dd3" />

8. Navigate to the same folder as in step 2 and select the .py file you downloaded.

9. Go to https://dev.twitch.tv/console/apps and create an application.

   <img width="267" height="77" alt="image" src="https://github.com/user-attachments/assets/2559dd5d-a460-4850-a3fd-d684be4a318d" />

11. Name the application however you want and in `OAuth Redirect URLs` paste this in:
     ```json
     http://localhost
  Like so:
  <img width="971" height="279" alt="image" src="https://github.com/user-attachments/assets/ae94c407-d23a-4032-a5fd-3beba27661f3" />

10. Select the `Aplication integration` as your category and complete the captcha and save your application. Client type `confidential`.

11. If you get sent back to the `Developer Applications` click on the `Manage` button of the application you just created.

12. At the bottom you will now have your `Client ID` which you will paste into the script config generator inside the `Scripts` menu of OBS in the `Twitch Client ID` text box.

<img width="942" height="701" alt="image" src="https://github.com/user-attachments/assets/90ce24bc-eb6a-408f-8859-6cadd65c7f42" />

13. Also on the same page you will need to generate a `New Secret` which you will paste in OBS in the `Twitch Client Secret` text box.

14. For `Broadcaster Username` you just write your twitch name as it appears in the URL bar when you go to your stream in browser `twitch.tv/[Username]`.

15. Click `Save Configuration` which will create a `config.json` file using the 3 text boxes and the last step is click `Login with Twitch` which will open your browser and if done correctly a text will appear on the page stating `Authentication successful! You can close this window.`.

16. Done!
You can add a custom game which will take priority over the discord database. in `EXE Name` write the name of the exe file you want: example: `gta4.exe` and in Twitch Category write the category you want to be set when detecting the process of the exe file. example: `Grand Theft Auto IV`.

Please note that you must enter the category exactly is it's displayed in twitch for it to work properly. (Not tested otherwise)

Inside Script Logs you can see some details about what the scripts does and when.
Example:
 ```json
 [TwitchAutoCategory - DiscordDB Implementation.py] Loaded 5 custom game mappings.
 [TwitchAutoCategory - DiscordDB Implementation.py] Process monitor started.
 [TwitchAutoCategory - DiscordDB Implementation.py] Loaded Discord DB cache (12131 executables).
 [Unknown Script] ✓ Updated Twitch category to: Megabonk
 [Unknown Script] OAuth server started on port 17563. Opening browser...
 [Unknown Script] Successfully logged in to Twitch!
 [Unknown Script] OAuth server started on port 17563. Opening browser...
 [Unknown Script] Successfully logged in to Twitch!
 [Unknown Script] OAuth server started on port 17563. Opening browser...
 [Unknown Script] Successfully logged in to Twitch!
```

```This plugin is licensed under GPLv3. You are free to use, modify, and distribute it, but any derivative work must also be open-source under the same license.```
