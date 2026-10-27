# Committee applications

Run from the project root with Python 3 and the standard library:

```sh
python3 site/server/applications.py
```

The server binds to `127.0.0.1:4174`. Open the public application form at <http://127.0.0.1:4174/apply/> and the password-protected workspace at <http://127.0.0.1:4174/committee/>. A static file server alone cannot save applications or run the workspace.

## Private storage and sign-in

The default private directory is `~/Document/HikingClubData`, outside the website root and using `Document` in the singular. On first launch, the server generates `admin-password.txt` there; use that password to sign in. The startup output identifies the path without printing the password. `HC_ADMIN_PASSWORD` can supply a password of at least 12 characters instead.

Applications, review statuses, committee notes, interviews and the notification queue persist in `applications.sqlite3`; SMTP configuration persists in `settings.json`. Restarting the server preserves these records and ends existing sign-in sessions. Keep this directory private and outside the repository; do not commit its files. `--data-dir` changes its location, and the server rejects storage inside the website root.

## Applications and notifications

The form collects personal details, programme/year, experience, interests, one or more roles and contact consent. The eight role definitions come from `site/data/committee-roles.json`. A successful submission saves the application and queues a committee notification together; email setup or delivery failure does not prevent persistence.

In **Email settings**, set the committee notification inbox, website URL, SMTP host, port, encryption, sender, username and password. STARTTLS and SSL/TLS are supported. Leave the password blank to retain it; changing the SMTP host or username can require re-entering it. The website URL supplies the private review link in notification messages.

Notifications wait until SMTP is configured, then the server worker attempts delivery automatically. Use **Refresh** to inspect queued, sent and failed counts, **Send a test email** to test delivery, and **Retry failed notifications** after correcting a delivery problem. These actions send email only when explicitly used or when a configured queue is processed. Changing the inbox affects new applications; already-addressed notifications retain their original recipient. `--notify-email committee@example.com` can seed the inbox on first launch; later changes belong in the workspace.

## Review and interviews

Use search, role, status and programme filters to find applications. Open a candidate to save a review status and private notes, or book an interview for a role that candidate selected.

For a batch, mark candidates **Shortlisted**, open **Interview agenda**, then choose a time window, interview length, break, role, interviewer/panel and location. **Preview agenda** prepares one slot per eligible shortlisted candidate without an existing interview. Review the preview and any candidates left without a slot, then select **Confirm interview schedule** to save it. Editing planner inputs clears the preview. Times use `Europe/Stockholm`.

Saving checks overlapping interviews for the same candidate or the same interviewer/panel name, including conflicts introduced after a preview. Use a consistent panel name: the server compares that name, not individual panel members. Failed batch conflict checks save no partial batch. Interviews can be cancelled from the agenda.

**Export calendar** downloads the authenticated, private ICS calendar. It contains candidate information; share it only with intended committee members. Booking, cancellation and export do not send candidate invitations. Arrange candidate communication separately.

## Development and verification

Relevant sources are `apply/index.html`, `committee/index.html`, `site/assets/css/committee.css`, `site/assets/js/committee-apply.js`, `site/assets/js/committee-admin.js` and `site/server/applications.py`. Recruitment pages reuse the existing official logos, paper/navy/pine palette, Newsreader headings and Schibsted Grotesk interface text. Their added layout uses labelled native fields, fieldsets, ruled rows and the planner preview/confirmation flow.

Run the integration checks from the project root:

```sh
python3 site/tools/check_applications.py
```

Checks use temporary data and simulated mail delivery; they do not send real emails. Browser visual verification remains outstanding, so this documentation makes no rendered-layout or computed-style claims.

This setup is local. Public hosting requires a backend that serves the API, private persistent storage and HTTPS; uploading only the static pages is insufficient. Deployment has not been authorised or performed.
