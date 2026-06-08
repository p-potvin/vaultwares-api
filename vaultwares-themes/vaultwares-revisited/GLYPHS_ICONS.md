# VaultWares Revisited: Glyphs & Icons

## Overview

Icons and glyphs in VaultWares Revisited are stark, utilitarian, and clean. They borrow heavily from technical schematics and HUD (Heads-Up Display) elements.

## Primary Icon Library

Categorized React TSX components in `vaultwares-revisited/icons/`:

| File | Categories |
| ----- | ------ |
| `navigation.tsx` | Dashboard, Menu, Settings, Search, Bell, User, Chevrons, Close, Check, Plus, Minus, Home |
| `actions.tsx` | Edit, Trash, Copy, Download, Upload, ExternalLink, Filter, Refresh, Save, Link, GitCommit |
| `monitoring.tsx` | Activity, BarChart, TrendUp/Down, AlertTriangle, Info, Clock, Calendar, Zap, PieChart |
| `security.tsx` | Shield variants, Lock/Unlock, Key, Fingerprint, Eye, Scan, Bug, Hash |
| `media.tsx` | Play, Pause, Stop, Skip, Volume |
| `data.tsx` | Database, Server, Terminal, Document, FileText, Folder, List, Code |
| `communication.tsx` | Mail, Phone, MessageSquare, Send, Globe |
| `index.ts` | Barrel re-export of all categories |

- **Stroke Width:** Generally bounded at `1.5` to `2` to ensure crispness on high-density displays.
- **Coloring:** Never hardcoded. Icons must inherit `currentColor` or be specifically bound to `var(--vault-console-*)` depending on state.

## Rules for Usage

1. **Action Icons:**
   Should highlight only on interaction (hover/focus), shifting from `--vault-console-text-secondary` to `--vault-console-gold`.
2. **Status Icons:**
   Use the Signal Palette (`--vault-signal-online`, `--vault-signal-warning`, etc.) to denote status. Accompany with `.vw-led` animation if the status represents an active, ongoing connection.
3. **Sizing:**
   Use standard tailwind sizes (`w-5 h-5`, `w-6 h-6`, etc.) or standard rem scaling (`1.25rem`, `1.5rem`). Avoid arbitrary sub-pixel scaling.
