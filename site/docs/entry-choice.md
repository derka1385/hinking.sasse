# Shared Hiking Club entrance

Local preview: http://127.0.0.1:4174/?intro. No commit, push or deployment.

The home page first presents two equal full-height choices, with only their names visible: Mountaineering on the left and Hiking on the right. The colours are Figma navy `#0B1B2E` and pine `#0E241D` (confirmed on node `111:100` in `TDPR8NqtknrV2GWdqU0spp`). Both are native links with visible keyboard focus; the columns retain that order on narrow screens.

On a fine-pointer hover, the selected panel grows to 56% while the other shrinks to 44%. The panels scale horizontally; inverse transforms keep their type and photos in proportion. Only transforms and opacity transition, with no animated grid layout. Releasing the hover reverses the same transition. Reduced motion keeps equal widths and shows the preview immediately. Keyboard focus and a touch press also reveal the preview without moving the panel.

The photographic preview fades to opacity .34 over the discipline colour, retaining the two colours and readable names. Mountaineering uses the site's existing `kebnekaise-ridge-1920.webp`. Hiking uses an optimized WebP of the exact local `brand-figma/assets/IMG_5274.jpg` photo, confirmed against Figma photo node `3:110`; the brand documentation identifies this group-in-forest photo as a story asset. The original image is unchanged. No temporary Figma URL is used at runtime.

The official symbol and horizontal wordmark are centred above the two choices. Their entrance uses a .65-second fade and 10-pixel rise, with a 70-millisecond stagger for the wordmark; the logo remains in that header position. Reduced motion uses a short fade only. Existing vector symbols are reused without editing their geometry.

On a fine mouse pointer, the entrance replaces the native cursor with a 30-pixel ring and central dot. The ring expands over links and contracts on press. `entry-choice.js` paints only after a pointer move and coalesces events into one frame; it runs no idle animation loop. The native pointer is hidden only after the replacement has been positioned. Keyboard use, touch input, leaving the entrance, page hiding, window blur and motion-preference changes restore the native cursor and cancel pending frames. Touch devices and reduced-motion users keep the native pointer. The circle never intercepts clicks or adds a keyboard stop, and the script returns immediately on the Mountaineering page.

The blue link opens `/?experience=mountaineering&intro`, which starts the existing mountain and whiteout intro. The mountain does not fetch terrain, allocate WebGL or schedule frames while the entrance is displayed. Replay uses the same explicit Mountaineering URL. Existing `?p=` debug previews bypass the entrance. Without JavaScript the existing static home page remains available.

The green link opens `/hiking/`, an intentionally empty white HTML document reserved for the future Hiking website. It loads no scripts or images.

Validated: intro lifecycle tests including the entrance resource gate, route selection, link order, two-name-only content, asset dimensions, blank Hiking body, unchanged main-page content and HTTP responses. At the maximum photographic opacity, even a white image pixel retains at least 4.7:1 contrast with the paper lettering. Browser visual verification remains unavailable because of the browser access policy; no replacement browser automation was attempted.

The logo/cursor update additionally passed a VM interaction check covering initial native-pointer safety, frame coalescing, latest-coordinate painting, press/release feedback, keyboard/touch/blur/leave/pagehide restoration, reduced motion, zero listeners on unsupported devices and unchanged main-page HTML. The mechanical design scan added no findings relative to the previous entrance.
