# How it works

## Screen readers stay in charge

A screen reader reads the page's accessibility tree with the keyboard, and when it reaches an image it speaks the image's alt text. Twitter and Reddit leave alt text to the poster, so most images have none, and videos get no description at all. This plugin writes its description into the image's alt text, starting with "Description:", so NVDA, JAWS or VoiceOver read it exactly where the image is. Video narration goes into a polite live region, which screen readers announce without moving your focus.

## Nothing is spent without a choice behind it

The plugin starts in manual mode, where nothing is sent until you press Alt+Shift+D. Auto mode, which you switch on yourself, describes images with no alt text as you reach them and narrates videos as they play. Images that already have alt text are only described when Replace existing alt text is on, and the original is read after the new description.

For videos 10 minutes or longer, the plugin first reads the length and the cost range of narrating it. While narrating, it checks a frame every 3 seconds and sends one to the model only when the picture has really changed. Narration stops when the video pauses or ends or you scroll past it, and it stops at the per-video limit you set, 0.05 dollars to start.

Two guards always apply: at most 20 descriptions a minute, and the daily ceiling you set. Warnings are read at half and at 90 percent of the ceiling.

## Prices

Prices come from OpenRouter's public model list, cached for a day. Hermes does not yet report the cost of plugin model calls, so the plugin works out each call's cost from its token counts and the model's price, and keeps a daily total. After 20 descriptions on a model, estimates switch from starting assumptions to your real averages.

Starting estimates use token counts measured on real calls: Gemini models bill about 1,250 input tokens per image whatever its size, and other models about 450 for a 768 pixel image, with about 60 output tokens. Video frames are 512 pixels wide, with 6 frames a minute described for a calm video and up to 20 for a busy one. In testing, a busy 16 second scene of an animated film used 5 frames.

| Model | Images per dollar | One hour of video, in dollars |
|---|---|---|
| Qwen 3.7 Flash | about 46,900 | 0.0076 to 0.03 dollars |
| Gemini 2.5 Flash Lite | about 6,700 | 0.05 to 0.17 dollars |
| Gemini 3.1 Flash Lite (default) | about 2,500 | 0.14 to 0.47 dollars |
| Gemini 3.1 Flash Image | about 1,200 | 0.28 to 0.93 dollars |
| Gemini 3.5 Flash | about 400 | 0.84 to 2.79 dollars |
| Gemini 3.1 Pro | about 300 | 1.12 to 3.72 dollars |
| Gemma 4 (free, rate limited) | free | free |

Switching to a model that costs over 1 dollar for an hour of busy video asks for confirmation. Reasoning is turned off in each request, because hidden reasoning tokens are billed.

## How the two parts fit

The Chrome extension runs in your own browser with your normal sign-ins. It finds images and videos, adds the describe buttons, captures the image or video frame you ask about, and reads results through your screen reader. It never talks to the internet itself except to load the image you asked about.

The Hermes plugin does everything else. Vision calls run through a plugin auxiliary task named visual_description, which uses the OpenRouter key Hermes already holds, so neither part ever sees the key. The plugin also keeps your settings, the prices, the spending guard and the daily total. The AI voice option uses Hermes's text_to_speech tool, so it speaks with whichever provider Hermes is set to, such as ElevenLabs.

The two talk over a connection on your own computer only, at 127.0.0.1 port 47823. The plugin accepts a request only when it comes from this extension's fixed ID, which websites cannot pretend to be, and only at the loopback address.

Images are shrunk to 768 pixels on the long side as JPEG quality 80 before they are sent, and video frames to 512 pixels wide. Results are cached by image address, so scrolling back or seeing a repost costs nothing.

## Limits

Streaming services protected by DRM, such as Netflix, return black frames, and the plugin says it cannot describe protected video. Videos inside cross-origin embeds can be described frame by frame with Alt+Shift+D, but their play and pause state is not visible to the page.

## Disclosures

The plugin runs a small server on your own computer, at 127.0.0.1 port 47823, while Hermes is open, so the Chrome extension can reach it. It only answers the bundled extension, checked by its fixed extension ID and the loopback address.

The extension, which you load yourself, captures the visible tab to crop out the image or video frame you're on, and adds descriptions to the page's alt text.

Images and video frames are shrunk and sent to the vision model set for the plugin, OpenRouter by default, using the key you added to Hermes. If the extension sends an image's address instead of a capture, the plugin downloads the image from that address.

The plugin fetches OpenRouter's public model price list, with no key. The AI voice goes through Hermes's own text to speech, using whichever provider Hermes is set to.

Your settings and daily spending are stored in Hermes. The last few video narrations are kept for 10 minutes and added to your Hermes chat, so you can ask about what you watched. The plugin runs no shell commands and reads no files outside Hermes.
