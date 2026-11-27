# Connecting Microsoft Teams (live sessions and workshops)

LearnHub creates Teams meetings for program sessions and workshops, reads who attended, and
copies the recording and transcript to the video service. Each provider connects **its own**
Microsoft 365 tenant (plan D19). Until it is connected, everything still works by hand: staff
paste a meeting link, mark attendance and upload the recording.

You need a Microsoft 365 admin (Global admin or Application admin, plus Teams admin for step 4).

## 1. Register the app
1. Azure portal → **Microsoft Entra ID** → **App registrations** → **New registration**.
2. Name: `LearnHub live sessions`. Supported accounts: *this organisational directory only*.
   No redirect URI.
3. Note the **Application (client) ID** and **Directory (tenant) ID**.

## 2. Add a client secret
**Certificates & secrets** → **New client secret** → 24 months. Copy the **Value** now (it is shown once).

## 3. Give the app permissions (application permissions, not delegated)
**API permissions** → **Add a permission** → **Microsoft Graph** → **Application permissions**:

| Permission | Why |
|---|---|
| `OnlineMeetings.ReadWrite.All` | create and move meetings |
| `OnlineMeetingArtifact.Read.All` | attendance reports |
| `OnlineMeetingRecording.Read.All` | download recordings |
| `OnlineMeetingTranscript.Read.All` | read transcripts |
| `Mail.Send` | only if LearnHub also sends email through Graph (already used for email) |

Then **Grant admin consent**.

## 4. Allow the app to act for the organiser (application access policy)
Meetings are created on behalf of one organiser account (for example `contact+1c176810c617@example.com`).
Teams requires an application access policy for that. In PowerShell, as a Teams admin:

```powershell
Install-Module MicrosoftTeams
Connect-MicrosoftTeams
New-CsApplicationAccessPolicy -Identity LearnHub-Live -AppIds "<Application (client) ID>" -Description "LearnHub live sessions"
Grant-CsApplicationAccessPolicy -PolicyName LearnHub-Live -Identity "contact+1c176810c617@example.com"
```

The policy can take up to 30 minutes to apply.

## 5. Recordings
- Meetings are created with **record automatically** on. The organiser's Teams meeting policy must
  allow cloud recording and transcription (Teams admin centre → Meetings → Meeting policies →
  *Recording & transcription*).
- Recordings are saved to the organiser's OneDrive. About 30 minutes after a session ends
  (setting **Minutes after a Teams session ends before its recording is copied**), LearnHub copies the
  recording to the video service and keeps the transcript. It tries up to 5 times.

## 6. Put the values in `backend/.env` (never in code or chat)

```
MICROSOFT_TENANT_ID=<Directory (tenant) ID>
MICROSOFT_CLIENT_ID=<Application (client) ID>
MICROSOFT_CLIENT_SECRET=<secret value>
TEAMS_MEETING_ORGANIZER=contact+1c176810c617@example.com
```

Restart the API and the Celery worker and beat. **Console → Programs → My teaching / Workshops** then
says "Teams meetings are created for you".

## Settings you can change (Console → Settings → Learning)
- **Minutes in a live session that count as present** (default 3).
- **Minutes before a live session the join link appears** (default 15).
- **Minutes after a Teams session ends before its recording is copied** (default 30).

## Notes
- Learners only ever receive the attendee join link, and only shortly before and during the session.
  The organiser's link and the app secret never leave the server.
- Attendance is matched by email address. People who join as guests without an email can't be matched.
  Staff can always correct attendance by hand, and a staff mark is never overwritten by Teams.
