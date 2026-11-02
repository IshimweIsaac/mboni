# Mboni: HCI design justification

## 1. Users and context

| Persona | Situation | What they need |
|---|---|---|
| **Keza, 21, student in Kigali** | Android phone, buys data bundles, pays with MoMo | Cheap access, low data use, no card |
| **Jean, 38, parent in Musanze** | Shares one account with three children | Profiles, a safe Kids space, French/Kinyarwanda |
| **Aisha, 29, professional in Nairobi** | Laptop and phone, wants new releases | Rent premieres without a subscription |
| **The admin / distributor** | Runs the catalogue | Revenue insight, failed payments, filmmaker payouts |

Design constraints from the context: expensive mobile data, unstable connections, mobile money instead of cards, several languages, shared family devices.

## 2. How the design answers those constraints

| Constraint | Design decision | Where |
|---|---|---|
| Data costs money | Data saver mode (240p); MB/hour shown in the player; total MB estimate on every film page; preview video removed when data saver is on | Settings, film page, player |
| Unstable network | Installable PWA, offline page, downloads that play offline (with seeking), offline banner | Library, service worker |
| No bank card | MTN MoMo and Airtel Money first, with a familiar USSD-style approval screen and the dial code shown | Checkout, pay page |
| Subscriptions do not suit everyone | Three ways to pay: subscribe, rent 48h, buy; prices shown per day and in USD | Plans, film page |
| Many languages | Interface in English, Kinyarwanda, French; subtitles in all three | Globe menu, player |
| Shared devices | Profiles, Kids profiles that filter the whole catalogue | Profiles page |

## 3. Nielsen's 10 heuristics

1. **Visibility of system status**: rental countdown ticking live; progress bars on cards; checkout steps (Choose, Pay, Watch); spinner on "Pay" while the request is sent; toasts after every action; on-screen display in the player ("+10s", "Muted").
2. **Match with the real world**: prices in RWF, "Rent for 48 hours", MoMo/Airtel colours, USSD prompt text, Kinyarwanda greetings ("Murakoze!"), African textile patterns on posters.
3. **User control and freedom**: Cancel payment button; cancel subscription keeps access to the paid date; remove downloads; Up-next can be cancelled; Esc closes overlays and the player.
4. **Consistency and standards**: one button system (gold = main action), same card everywhere, standard player shortcuts (Space, ←/→, F, M, C).
5. **Error prevention**: phone checked against the chosen network's prefixes; card number formatted while typing; expiry auto-slash; confirmation dialog before deleting profiles, films or cancelling a plan; renting an owned film is blocked.
6. **Recognition rather than recall**: Continue watching, My List, history, "Because you watched", search suggestions, mood chips.
7. **Flexibility and efficiency**: `/` to search from anywhere, voice search, keyboard player control, double-tap to skip, one-click demo login, promo code applied without reloading.
8. **Aesthetic and minimalist design**: dark cinema theme, content first, details on demand (film page, settings sheet in the player).
9. **Help users recover from errors**: every field error says what is wrong and gives an example ("Use a Rwandan number like 0788123456"); failed payments say "Nothing was charged" and offer Try again; friendly 404/403 pages.
10. **Help and documentation**: FAQ on the landing page, hints under form fields, keyboard shortcuts listed in the player.

## 4. Accessibility (WCAG 2.1 AA)

- Skip-to-content link; every page keyboard navigable with a visible gold focus ring
- ARIA: `aria-current` on navigation, `aria-pressed` on toggles, `aria-invalid` + `aria-describedby` on form errors, tabs with arrow-key support, player seek bar is a `role="slider"` with `aria-valuetext`, live regions for toasts and search results
- Text alternatives: every icon button has an `aria-label`; poster cards announce title, year and country
- Subtitles in three languages
- High contrast mode, light theme, and Reduce motion (also respects the OS `prefers-reduced-motion` setting)
- Touch targets at least 44px; bottom tab bar within thumb reach on phones

## 5. Responsive design

- Mobile first: bottom tab bar under 760px, top navigation above
- Rows scroll horizontally with snap on phones, arrow buttons on desktop
- Hero becomes a bottom-anchored layout on phones and supports swipe
- Checkout and film pages collapse to one column; order summary moves to the top on phones
- Tested at 390px (phone), 768px (tablet) and 1920px (desktop)

## 6. Evaluation plan

| Task | Success measure |
|---|---|
| Find a Kinyarwanda film and add it to My List | < 30 s, no errors |
| Rent a premiere with MoMo using a promo code | < 60 s, correct total shown before paying |
| Switch to data saver and start a film | user can say how much data it will use |
| Create a Kids profile and check what it shows | no 16+ or 18+ films visible |
| Admin: find how much is owed to filmmakers | < 15 s |

Use think-aloud with 5 users, then a SUS questionnaire (target score above 75).
