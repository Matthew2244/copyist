# Copyist for macOS

SwiftUI. No canvas, no custom control templates, no custom `NSAccessibilityElement` —
lists, forms and buttons only, so VoiceOver gets name, role and value for free.

```bash
swift build
./.build/debug/Copyist
```

The app needs `prototype/engine.py`. It looks beside the binary, then up the
tree, then at `$COPYIST_ENGINE`.

## Verifying accessibility

`axaudit` inspects a running Copyist the way a screen reader does and fails if
any interactive control has no name a screen reader could speak.

```bash
./.build/debug/Copyist &
./.build/debug/axaudit Copyist
```

**It needs the Accessibility permission**, granted to whatever terminal runs it:
System Settings → Privacy & Security → Accessibility. That requires your
password and a physical toggle — macOS does not allow it to be granted by a
script, and it should not.

**Leave VoiceOver ON while auditing.** The accessibility tree is built lazily
when an assistive client attaches; with VoiceOver off there is less to inspect,
and a thin tree reads as "no problems found" when in fact nothing was looked at.
Both auditors exit 2 rather than 0 in that case, on purpose.

`Copyist --audit` exists too but can only see the window frame. SwiftUI does not
expose its tree through the AppKit object graph a process can walk from inside
itself, so in-process self-inspection cannot work here. That is documented at
the top of `Sources/axaudit/main.swift`.
