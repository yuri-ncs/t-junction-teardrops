# Changelog

## 0.4.3
- The clearance check looks as far as the board's biggest clearance, instead of a fixed 1 mm.

## 0.4.2
- Max corner angle defaults to 120° (was 179°). The limit is inclusive and the angle is rounded to 0.1°, so the three corners of a
  120° Y are treated alike.
- New *Min length (% of width)* parameter, 25 % by default: a fillet cut short by a pad or via is not made.
- A fillet stops short of other nets' copper by that copper's clearance, so the zone fill no longer leaves a copper horn.

## 0.4.1
- A fillet stops at the first pad or via of its own net.
- A branch that leaves from the middle of a segment measures the free length on each side separately.

## 0.4.0
- *Exclude nets* (patterns) and *Exclude net classes*.
- Out-of-date line with an *Update out-of-date* button.

## 0.3.0
- Parameter dialog with a live preview.
- *Remove* mode replaces the separate remove action.

## 0.2.2
- Identifier `com.teardropt` and the author's e-mail in the metadata.

## 0.2.1
- New toolbar icon for the light and dark themes, and a 64 px icon for the Plugin and Content Manager.

## 0.2.0
- One zone per corner, holding the half track, so the fill reaches the tangent points.

## 0.1.1
- Fill down to 0.0254 mm.
