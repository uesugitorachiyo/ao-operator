# Service Booking Recovery App - Outcome SDD

## Outcome

Build a first-screen web app for a small service business owner who says:

> I miss booking requests when I am busy. I want one screen that shows open
> requests, the next action for each customer, and the revenue I can still save
> today.

The user is not asking for a framework, library, or code structure. They want a
working local app they can open, inspect, and adapt.

## Users

- Owner/operator who answers calls between jobs.
- Dispatcher who follows up with open booking requests.
- Assistant who needs a simple daily view without CRM training.

## First Screen Requirements

- Show total open requests, urgent requests, scheduled requests, and saveable
  revenue.
- Capture a new booking request with customer name, requested service, urgency,
  requested window, and estimated value.
- Generate a plain-language next-action note from those details.
- Group requests by `new`, `follow-up`, `scheduled`, and `lost`.
- Keep all data local and synthetic for the demo.

## Acceptance Criteria

- The app can run as static HTML/CSS/JS.
- A verifier can confirm the seed data, status grouping, revenue calculation,
  and required UI markers without browser automation.
- No SMS, email, payment, CRM, or phone-provider integration is active.
- The deliverable includes a README that explains the business outcome first.

