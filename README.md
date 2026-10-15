# Shorts Bot

Makes one short vertical video twice a day and publishes it to **YouTube Shorts, Facebook Reels, Instagram Reels and (optionally) X**. It runs free on GitHub Actions, with a status dashboard on GitHub Pages.

```
Gemini (script) → edge-tts (voice) → Pixabay (footage) → ffmpeg (1080×1920 + captions)
        → YouTube · Facebook · Instagram · X → data/history.json → dashboard
```

- **Each platform is independent.** If Instagram fails, YouTube and Facebook still post, and the failure shows on the dashboard.
- **Missing credentials mean a skipped platform.** A platform without credentials is skipped, so you can set them up one at a time.
- **Failed videos are kept.** If any platform fails, the rendered video is kept for 7 days under the run's **Artifacts** so you can post it by hand.
- **GitHub emails you** when a run fails.

Schedule: 08:47 and 18:17 IST. Change the `cron` lines in `.github/workflows/post-short.yml`.

| Platform  | Cost | Needs app review? |
|-----------|------|-------------------|
| YouTube   | Free | One-time API audit for uploads to be public |
| Facebook  | Free | No (your own Page) |
| Instagram | Free | No (your own account) |
| X         | Paid, pay-per-use (no free API tier since Feb 2026) | No |

---

## Setup

### 1. Repo and dashboard
1. Create a **public** GitHub repo and push this folder to it. Public repos get free unlimited Actions minutes and free Pages.
2. **Settings → Pages →** Source: *Deploy from a branch*, Branch: `main` / `(root)`.
   The dashboard is at `https://<your-username>.github.io/<repo>/`, and the privacy policy is at `.../privacy.html`. Meta and Google ask for that privacy policy URL.
3. Secrets go in **Settings → Secrets and variables → Actions → Secrets**.

### 2. Content keys (required)
- **Gemini:** https://aistudio.google.com/apikey → secret `GEMINI_API_KEY`
- **Pixabay:** sign up at https://pixabay.com, then open https://pixabay.com/api/docs/ and your key appears there → secret `PIXABAY_API_KEY`
- *(Optional)* `PEXELS_API_KEY` if you already have one. It's used as an extra footage source.

Without any footage key, videos still render on an animated gradient background.

### 3. YouTube
1. Create a channel for this, ideally a Brand Account.
2. https://console.cloud.google.com → new project → **APIs & Services → Library** → enable **YouTube Data API v3**.
3. **OAuth consent screen:** External. Add your email, the privacy policy URL, the scope `.../auth/youtube.upload`, and yourself as a test user. Then click **Publish app** so the status reads *In production*. In *Testing* mode the token dies every 7 days.
4. **Credentials → OAuth client ID → Desktop app** → download as `client_secret.json`.
5. On your computer, run:
   ```
   pip install google-auth-oauthlib
   python get_token.py client_secret.json
   ```
   Click through the "unverified app" warning (Advanced → Go to app). Then add `YT_CLIENT_ID`, `YT_CLIENT_SECRET` and `YT_REFRESH_TOKEN` as secrets.
6. Submit the **YouTube API audit** so uploads aren't locked to private: https://support.google.com/youtube/contact/yt_api_form
   Until it's approved, videos upload as private. You can flip them to public in YouTube Studio.

### 4. Facebook + Instagram (one setup covers both)
1. **Facebook Page:** create a Page for the channel (free).
2. **Instagram:** in the app, go to **Settings → Account type and tools → Switch to professional account → Business**, then connect it to that Facebook Page.
3. **Meta app:** at https://developers.facebook.com → **Create App** → use case *Other* → type *Business*.
   Use a personal business portfolio, not your employer's.
4. **App settings → Basic:** add the privacy policy URL from step 1, then switch the app from *Development* to **Live** at the top. Posts from an app in development mode may only be visible to you.
5. **Get a token:** open the **Graph API Explorer** (https://developers.facebook.com/tools/explorer), select your app, choose *Get User Access Token*, and tick these permissions:
   `pages_show_list`, `pages_read_engagement`, `pages_manage_posts`, `instagram_basic`, `instagram_content_publish`, `business_management`
   Click **Generate Access Token** and approve for your Page and Instagram account.
6. On your computer, run:
   ```
   pip install requests
   python meta_token.py
   ```
   Paste the App ID, App Secret and the token from the Explorer. It prints `FB_PAGE_ID`, `META_PAGE_TOKEN` and `IG_USER_ID`, so add all three as secrets.
   The Page token does not expire. It only stops working if you change your Facebook password or remove the app.

### 5. X (optional, costs money)
X's API is pay-per-use, about $0.015 per post plus media charges shown in the console. At 2 posts a day that's a small monthly amount, but you need a card on file.
1. https://developer.x.com → create a project and app → enrol in pay-per-use billing and **set a monthly spend cap**. Turn auto-recharge off or keep it low.
2. **App → User authentication settings →** permissions **Read and write**.
3. **Keys and tokens:** copy the API Key/Secret, then *generate* the Access Token/Secret. Generate these after setting write permission, or posting fails with 403.
4. Add `X_API_KEY`, `X_API_SECRET`, `X_ACCESS_TOKEN` and `X_ACCESS_SECRET` as secrets.

Skip this section and the bot simply won't post to X.

### 6. Test it
**Actions → Post a Short → Run workflow.** You can type platforms (for example `youtube,instagram`) to test one at a time. Check the log, then the dashboard.

---

## Settings page

`https://<your-username>.github.io/<repo>/admin.html` lets you change the genre, tags, voice, platforms and posting times, post a video on demand, pause the schedule, and see recent runs.

The page itself is public, but it does nothing without a GitHub access key for your repo, and that key is only ever stored in your own browser. To sign in:
1. Click **Create an access key** on the page. The permissions are pre-filled.
2. Under **Repository access**, choose **Only select repositories** and pick this repo.
3. Click **Generate token** and paste the key into the page.

The key expires after a year. When it does, the page asks you to sign in again. The bot keeps posting either way, since it doesn't use this key.

## Settings by hand (Settings → Secrets and variables → Actions → **Variables**)
| Variable | Example | Default |
|----------|---------|---------|
| `NICHE` | `ancient history mysteries` | `surprising science and nature facts` |
| `PRIVACY_STATUS` | `unlisted` | `public` (YouTube only) |
| `PLATFORMS` | `youtube,facebook` | every platform with credentials |
| `FIXED_TAGS` | `facts,science` | none (AI tags only) |
| `TTS_VOICE` | `en-GB-RyanNeural` | `en-US-AndrewNeural` |
| `YT_CATEGORY` | `28` | `27` (Education) |
| `GEMINI_MODEL` | `gemini-3.8-flash` | `gemini-3.8-flash` |

## Maintenance you can expect
- **A failure email:** open the failed run and read which platform failed and why. Common causes are an expired token (redo that platform's token step) or a free-tier limit change.
- **Graph API versions** retire after about 2 years. If Meta calls start failing with a version error, set a variable `GRAPH_VERSION` to the current one, for example `v25.0`.
- **edge-tts** is unofficial. If voice generation breaks, run `pip install -U edge-tts` locally to check, or bump its version in `requirements.txt`.

## Making money
- **YouTube:** 1,000 subscribers plus 10M Shorts views in 90 days.
- **Facebook:** monetization has its own follower and view thresholds.
- **AI content:** fully templated AI content gets rejected or demonetized as "inauthentic." Use the dashboard to spot which videos do well and narrow `NICHE` toward them.
