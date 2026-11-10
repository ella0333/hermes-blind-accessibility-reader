# Blind Accessibility Video and Image Reader

A plugin for Hermes Agent that describes the images and videos you come across on any website, so blind and low vision people can follow along. It comes with a small Chrome extension that works in your normal browser, and it reads descriptions through your screen reader or out loud in an AI voice. You decide when it describes something and how much it can spend.

## Requirements

You need Hermes (the desktop app or the terminal version), Google Chrome and an OpenRouter key.

OpenRouter is the model provider the reader uses. One key gives you access to many different AI models, so you can switch to a cheaper or better one at any time without signing up anywhere else. Create a key at [openrouter.ai](https://openrouter.ai) and set a spending limit on it there as well, as an extra safety net on top of the reader's own daily limit.

## Setup

**Hermes Desktop**

1. Open Settings, go to Providers and then API keys, and add your OpenRouter key.
2. In Settings, go to Plugins, choose Install from Git and paste `https://github.com/ella0333/hermes-blind-accessibility-reader`.
3. In a chat, type `/describe extension` to see where the Chrome extension was saved.

**Hermes in a terminal**

1. Run `hermes setup` and add your OpenRouter key when it asks.
2. Run `hermes plugins install https://github.com/ella0333/hermes-blind-accessibility-reader.git`.
3. Run `hermes describe extension` to see where the Chrome extension was saved.

**Chrome**

Open `chrome://extensions`, turn on Developer mode, choose Load unpacked and pick the folder from step 3. Then press Alt+Shift+S in any tab to open the reader's settings and choose how you'd like it to work.

Hermes needs to stay open while you browse, because it's what talks to the AI model.

**AI voice**

The AI voice is Hermes's own text to speech. It uses a free voice unless you choose another provider, and the demo video uses ElevenLabs with an ElevenLabs key added to Hermes. To do the same in Hermes Desktop, add your ElevenLabs key in Settings under Tools & Keys, then go to Voice, open Text to speech and set the provider to ElevenLabs. In a terminal, run `hermes setup tts` and choose ElevenLabs. Then pick the AI voice in the reader's settings with Alt+Shift+S.

The plugin's voice in the demo video is the ElevenLabs voice Brian, with voice ID `Gubgw9l4dtIoQA9YZHgx` and the `eleven_v4_turbo` model. You can set both on the same Text to speech page in Hermes Desktop, or with `hermes config set tts.elevenlabs.voice_id Gubgw9l4dtIoQA9YZHgx` in a terminal. The video's narration is the ElevenLabs voice Amy.

## Auto mode

Scroll through any page, and whatever image or video you scroll to is described for you. When you land on something, you'll hear a short tone and see a blue outline around it, and then the description is read out. Videos are narrated scene by scene while they play. You don't need any shortcuts in auto mode.

On YouTube playlists, you may need to refresh the page for the reader to pick up the next video.

## Manual mode

Nothing is described until you ask, so nothing is spent until you ask. As you scroll, the blue outline and tone still show which image or video you're on, and you use these shortcuts:

| Shortcut | What it does |
|---|---|
| Alt+Shift+Period | Moves to the next image or video |
| Alt+Shift+D | Describes the image, or starts and stops narrating the video |
| Alt+Shift+4 | Tells you the cost and how much you've spent today |

In both modes, Alt+Shift+S opens the settings, and you can change any shortcut at `chrome://extensions/shortcuts`.

## Configuration

| Setting | What it does |
|---|---|
| Mode | Auto describes as you scroll. Manual waits for Alt+Shift+D. |
| Where descriptions are read | Your screen reader, the free browser voice, or an AI voice through Hermes, such as ElevenLabs. |
| Model | The AI model that describes things, with its price shown. |
| Daily spending limit | Stops for the day at this amount. Starts at 50 cents. |
| Most to spend on one video | Stops narrating a single video at this amount. Starts at 5 cents. |
| Show captions on screen | Shows what's being read at the bottom of the page. |
| Play a sound | Plays a tone when the reader moves to something new. |
| Read captions and titles | Reads post text and titles before the description. |
| Replace existing alt text | Also describes images that already have alt text. |

## Cost

With the default model, one image costs about 0.0004 dollars, so a dollar covers about 2,500 images. Narrating a minute of video costs about 0.002 to 0.008 dollars, depending on how often the scene changes.

Costs are kept low by shrinking each image to 768 pixels on its longest side, and each video frame to 512 pixels, before it's sent to the model.

## Hermes commands

You can also manage the reader from a Hermes chat. Type `/describe` for a menu, `/describe setup` to answer the setup questions, or `/describe status` to see your settings and what you've spent today. You can ask Hermes things in your own words too, like "what's on my screen?" or "what happened in the video I just watched?"

## Disclosures

The plugin runs a small server on your own computer, at 127.0.0.1 port 47823, while Hermes is open, so the Chrome extension can reach it. It only answers the bundled extension, checked by its fixed extension ID and the loopback address.

The extension, which you load yourself, captures the visible tab to crop out the image or video frame you're on, and adds descriptions to the page's alt text.

Images and video frames are shrunk and sent to the vision model set for the plugin, OpenRouter by default, using the key you added to Hermes. If the extension sends an image's address instead of a capture, the plugin downloads the image from that address.

The plugin fetches OpenRouter's public model price list, with no key. The AI voice goes through Hermes's own text to speech, using whichever provider Hermes is set to.

Your settings and daily spending are stored in Hermes. The last few video narrations are kept for 10 minutes and added to your Hermes chat, so you can ask about what you watched. The plugin runs no shell commands and reads no files outside Hermes.

More detail about how it works, each model's price and what it sends where is in [HOW_IT_WORKS.md](HOW_IT_WORKS.md).

Made by Gabriella Baris.
