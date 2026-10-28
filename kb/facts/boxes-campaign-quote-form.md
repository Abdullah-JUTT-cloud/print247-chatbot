---
id: boxes-campaign-quote-form
title: Boxes quote form (boxes campaign page)
category: facts
source: boxes-campaign-main/src/app/components/home/banner/boxesForm/index.jsx, banner/modal/modal.jsx, customQuote/index.jsx
status: verified
last_reviewed: 2026-10-29
---

A boxes quote on the campaign page needs: box type (main form
dropdown), width (required), height (required), length (optional,
blank = 0), unit (inches/cm/mm, default inches), quantity of at least
1000, full name, email, and US phone (10-15 digits); note and artwork
files are optional. There is no preset size list — any numeric width
and height are accepted. Dimensions are submitted as width x height x
length. There is no material picker and no finish picker in the form,
and the company field is not shown in the live UI. Minimum order is
1000 units, enforced in the form and FAQ (the campaign page never says
"per size"). On success the visitor reaches a thank-you page, with a
quote number in the URL when the backend returns one, and a rep contacts
them with the quote — no day-count SLA is stated on this page.
