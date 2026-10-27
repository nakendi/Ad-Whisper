"""AdWhisper (by @saha12cheh) — Minimalist Dark UI.

Strict compliance with Design Specification:
- Dark surface tokens (#121314, #1A1C1E, #2A2D30, #3A3E42, #C8F169, #ECEBE6, #9A9C98, #3B4A14).
- Typography: Inter Tight (400, 500, 600) & JetBrains Mono (400, 500).
- Zero emojis. All icons are pure inline-SVGs (stroke 1.6, round caps) and white TikTok badge.
- Interactive filter tiles with dynamic view calculations matching active category.
- Inline working HTML5 audio player in table and publication cards.
"""

import os
from datetime import date, datetime, timedelta
from pathlib import Path

# Prepend local FFmpeg directories to front of PATH so WinGet/AppData are never used
_app_dir = Path(__file__).resolve().parent
for _cand in [_app_dir / "bin", _app_dir / "ffmpeg", _app_dir / "runtime" / "bin"]:
    if _cand.exists():
        os.environ["PATH"] = str(_cand) + os.pathsep + os.environ.get("PATH", "")
import base64
import html
import json
import re
import time
import urllib.parse
from typing import Any, Dict, List, Optional, Tuple, Union

import pandas as pd
from rapidfuzz import fuzz
import streamlit as st

from config import TARGET_VARIANTS, load_config
from database import Database
from exporter import ReportExporter
from matcher import PhraseMatcher
from scanner_engine import ScannerEngine
from collector import TikTokCollector
import updater

# 1. Icon & Page Configuration
icon_file_path = Path(__file__).resolve().parent / "app_icon.png"
icon_b64 = ""
if icon_file_path.exists():
    try:
        with open(icon_file_path, "rb") as f_ic:
            icon_b64 = base64.b64encode(f_ic.read()).decode("utf-8")
    except Exception:
        pass

st.set_page_config(
    page_title="AdWhisper (by @saha12cheh)",
    page_icon=str(icon_file_path) if icon_file_path.exists() else "https://www.tiktok.com/favicon.ico",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# 2. Design Tokens & Styling (AdWhisper Dark UI)
if icon_b64:
    st.markdown(f'<link rel="icon" type="image/png" href="data:image/png;base64,{icon_b64}"><link rel="shortcut icon" type="image/png" href="data:image/png;base64,{icon_b64}">', unsafe_allow_html=True)

# Minimal initial page loader (centered sleek rotating ring on black background)
if "has_loaded_once" not in st.session_state:
    st.session_state.has_loaded_once = True
    st.markdown("""
<div id="adwhisper-page-loader">
    <div class="sleek-loader-ring"></div>
</div>
""", unsafe_allow_html=True)

st.markdown("""
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Inter+Tight:wght@400;500;600&family=JetBrains+Mono:wght@400;500;600&display=swap" rel="stylesheet">

<style>
    /* Eradicate Streamlit default running banner / status indicator ("Running get_shared_transcriber()") */
    div[data-testid="stStatusWidget"],
    [data-testid="stStatusWidget"] * {
        display: none !important;
        visibility: hidden !important;
        opacity: 0 !important;
        height: 0 !important;
        width: 0 !important;
        pointer-events: none !important;
    }

    /* Minimal centered page load overlay matching pitch-black minimalist design */
    #adwhisper-page-loader {
        position: fixed;
        top: 0;
        left: 0;
        width: 100vw;
        height: 100vh;
        background-color: #0A0A0A;
        display: flex;
        align-items: center;
        justify-content: center;
        z-index: 9999999;
        pointer-events: none;
        opacity: 1;
        animation: fadeOutLoader 0.4s ease-out 0.6s forwards;
    }

    @keyframes fadeOutLoader {
        0% { opacity: 1; visibility: visible; }
        99% { opacity: 0; visibility: visible; }
        100% { opacity: 0; visibility: hidden; display: none; }
    }

    .sleek-loader-ring {
        width: 52px;
        height: 52px;
        border: 3.5px solid rgba(255, 255, 255, 0.08);
        border-top: 3.5px solid #ECEBE6;
        border-radius: 50%;
        animation: sleekSpin 0.75s cubic-bezier(0.4, 0, 0.2, 1) infinite;
    }

    @keyframes sleekSpin {
        0% { transform: rotate(0deg); }
        100% { transform: rotate(360deg); }
    }
    }

    .sleek-loader-ring {
        width: 60px;
        height: 60px;
        border: 4px solid rgba(255, 255, 255, 0.10);
        border-top: 4px solid #F1F5F9;
        border-radius: 50%;
        animation: ringSpin 0.85s linear infinite;
    }

    @keyframes ringSpin {
        0% { transform: rotate(0deg); }
        100% { transform: rotate(360deg); }
    }

    /* CSS Reset & Dark Background */
    html, body, [data-testid="stAppViewContainer"] {
        background-color: #121314 !important;
        color: #ECEBE6 !important;
        font-family: 'Inter Tight', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif !important;
        -webkit-font-smoothing: antialiased;
    }

    /* Hide Streamlit Headers, Sidebar, Toolbar, Deco */
    header[data-testid="stHeader"], div[data-testid="stToolbar"], div[data-testid="stDecoration"] {
        display: none !important;
    }
    [data-testid="stSidebar"], section[data-testid="stSidebar"], [data-testid="collapsedControl"] {
        display: none !important;
    }

    /* Centered Max-Width Container: 1280px, padding 32px 40px */
    .block-container {
        max-width: 1280px !important;
        margin: 0 auto !important;
        padding-top: 32px !important;
        padding-bottom: 48px !important;
        padding-left: 40px !important;
        padding-right: 40px !important;
    }

    /* Monospace elements */
    .mono {
        font-family: 'JetBrains Mono', monospace !important;
    }

    /* SECTION 1: HEADER */
    .banner-header {
        display: flex;
        align-items: center;
        justify-content: space-between;
        margin-bottom: 24px;
    }
    .header-left {
        display: flex;
        align-items: center;
        gap: 14px;
    }
    .header-titles {
        display: flex;
        flex-direction: column;
        gap: 2px;
    }
    .header-app-name {
        font-size: 20px;
        font-weight: 600;
        color: #ECEBE6;
        line-height: 1.2;
        letter-spacing: -0.01em;
    }
    .header-author {
        font-size: 13px;
        font-weight: 400;
        color: #9A9C98;
        line-height: 1.2;
    }
    .header-pills {
        display: flex;
        align-items: center;
        gap: 8px;
    }
    .header-pill {
        border: 1px solid #2A2D30;
        background: #121314;
        border-radius: 999px;
        padding: 5px 12px;
        font-family: 'JetBrains Mono', monospace;
        font-size: 12px;
        font-weight: 500;
        color: #CFCEC8;
        line-height: 1;
    }
    .header-update-btn {
        text-decoration: none !important;
        cursor: pointer;
        display: inline-flex;
        align-items: center;
        gap: 6px;
        transition: all 0.2s cubic-bezier(0.16, 1, 0.3, 1);
    }
    .header-update-btn:hover {
        border-color: #C8F169 !important;
        color: #ECEBE6 !important;
        transform: translateY(-1px);
    }
    .header-update-btn.has-update {
        border-color: #C8F169 !important;
        background: rgba(200, 241, 105, 0.12) !important;
        color: #C8F169 !important;
        font-weight: 600 !important;
        animation: pulse-update-badge 2.4s infinite ease-in-out;
    }
    @keyframes pulse-update-badge {
        0%, 100% { box-shadow: 0 0 0 0 rgba(200, 241, 105, 0.4); }
        50% { box-shadow: 0 0 0 4px rgba(200, 241, 105, 0); }
    }

    /* SECTION 2: PARAMETERS PANEL */
    div[data-testid="stVerticalBlockBorderWrapper"]:first-of-type,
    .params-container {
        background: #1A1C1E !important;
        border: 1px solid #2A2D30 !important;
        border-radius: 16px !important;
        padding: 24px !important;
        margin-bottom: 24px !important;
    }
    div[data-testid="column"] {
        background: transparent !important;
        border: none !important;
        padding: 0 !important;
    }
    div[data-testid="column"] div[data-testid="stVerticalBlockBorderWrapper"] {
        background: transparent !important;
        border: none !important;
        padding: 0 !important;
        margin: 0 !important;
    }
    .field-label {
        font-size: 12px;
        color: #9A9C98;
        font-weight: 400;
        margin-bottom: 6px;
    }

    /* Streamlit Input Overrides: distinct placeholder vs value, uniform borders */
    div[data-testid="stTextInput"] input,
    div[data-testid="stDateInput"] input,
    div[data-testid="stNumberInput"] input {
        height: 44px !important;
        background-color: #121314 !important;
        border: 1px solid #2A2D30 !important;
        border-radius: 10px !important;
        color: #ECEBE6 !important;
        font-family: 'JetBrains Mono', monospace !important;
        font-size: 14px !important;
        font-weight: 500 !important;
        padding: 0 14px !important;
        box-shadow: none !important;
    }
    div[data-baseweb="input"] {
        background-color: #121314 !important;
        border: 1px solid #2A2D30 !important;
        border-radius: 10px !important;
        box-shadow: none !important;
    }
    div[data-baseweb="base-input"] {
        background-color: #121314 !important;
        border: none !important;
    }
    div[data-baseweb="input"]:focus-within,
    div[data-testid="stTextInput"] input:focus,
    div[data-testid="stDateInput"] input:focus,
    div[data-testid="stNumberInput"] input:focus {
        border-color: #C8F169 !important;
        outline: 2px solid #C8F169 !important;
        outline-offset: 2px !important;
    }
    ::placeholder, input::placeholder, textarea::placeholder {
        color: #5A5D62 !important;
        font-style: italic !important;
        font-weight: 400 !important;
        opacity: 1 !important;
    }
    label[data-testid="stWidgetLabel"] p {
        font-family: 'Inter Tight', sans-serif !important;
        font-size: 12px !important;
        color: #9A9C98 !important;
        font-weight: 400 !important;
        margin-bottom: 6px !important;
    }

    /* Hide Step Buttons in Number Inputs */
    div[data-testid="stNumberInput"] button {
        display: none !important;
    }
    div[data-testid="stNumberInputContainer"] button {
        display: none !important;
    }
    div[data-testid="stNumberInputStepDown"],
    div[data-testid="stNumberInputStepUp"] {
        display: none !important;
    }

    /* Date Input overrides */
    div[data-testid="stDateInput"] button {
        color: #9A9C98 !important;
        border: none !important;
        background: transparent !important;
    }

    /* Chip buttons styling (Row 1) */
    div.chip-btn-wrap div.stButton > button,
    div.stButton > button[kind="secondary"] {
        height: 44px !important;
        background: #1A1C1E !important;
        border: 1px solid #2A2D30 !important;
        border-radius: 10px !important;
        color: #ECEBE6 !important;
        font-family: 'Inter Tight', sans-serif !important;
        font-size: 14px !important;
        font-weight: 500 !important;
        padding: 0 14px !important;
        transition: border-color 0.15s ease !important;
        width: 100% !important;
        box-shadow: none !important;
    }
    div.chip-btn-wrap div.stButton > button:hover,
    div.stButton > button[kind="secondary"]:hover {
        border-color: #3A3E42 !important;
        background: #1A1C1E !important;
        color: #FFFFFF !important;
    }

    /* Run Scan Button: Bright Lime Accent */
    button[kind="primary"],
    button[data-testid="stBaseButton-primary"],
    div.stButton > button[kind="primary"],
    div.stButton > button[data-testid="stBaseButton-primary"],
    div.scan-btn-wrap div.stButton > button {
        height: 44px !important;
        background-color: #C8F169 !important;
        background: #C8F169 !important;
        border: none !important;
        border-radius: 10px !important;
        color: #121314 !important;
        font-family: 'Inter Tight', sans-serif !important;
        font-size: 15px !important;
        font-weight: 600 !important;
        padding: 0 20px !important;
        cursor: pointer !important;
        width: 100% !important;
        box-shadow: none !important;
        transition: background-color 0.15s ease !important;
    }
    button[kind="primary"]:hover,
    button[data-testid="stBaseButton-primary"]:hover,
    div.scan-btn-wrap div.stButton > button:hover {
        background-color: #d5f583 !important;
        background: #d5f583 !important;
        color: #121314 !important;
    }
    button[kind="primary"]:focus,
    button[data-testid="stBaseButton-primary"]:focus,
    div.scan-btn-wrap div.stButton > button:focus {
        outline: 2px solid #C8F169 !important;
        outline-offset: 2px !important;
    }
    button[kind="primary"]:disabled,
    button[data-testid="stBaseButton-primary"]:disabled {
        background: #2A2D30 !important;
        color: #9A9C98 !important;
        cursor: not-allowed !important;
    }

    /* Slider accent & Track */
    div[data-testid="stSlider"] div[data-baseweb="slider"] {
        margin-top: 6px !important;
    }
    div[data-testid="stSlider"] div[role="slider"] {
        background-color: #C8F169 !important;
        border: none !important;
        width: 14px !important;
        height: 14px !important;
        box-shadow: none !important;
        top: -5px !important;
    }
    div[data-testid="stSlider"] div[role="slider"] > div {
        display: none !important;
    }
    div[data-testid="stSlider"] div[data-baseweb="slider"] > div > div:first-child {
        background: #2A2D30 !important;
        height: 4px !important;
        border-radius: 2px !important;
    }
    div[data-testid="stSlider"] div[data-baseweb="slider"] > div > div:first-child > div:first-child {
        background: #C8F169 !important;
        height: 4px !important;
        border-radius: 2px !important;
    }
    div[data-testid="stSlider"] div[data-testid="stTickBar"] {
        display: none !important;
    }

    /* Advanced Settings Expander: Sleek Accordion */
    div[data-testid="stExpander"] {
        background: #141517 !important;
        border: 0.5px solid #2A2D30 !important;
        border-radius: 12px !important;
        box-shadow: none !important;
        padding: 0 !important;
        margin-top: 14px !important;
        margin-bottom: 16px !important;
        overflow: hidden !important;
        transition: border-color 0.2s ease !important;
    }
    div[data-testid="stExpander"]:hover {
        border-color: #3A3E42 !important;
    }
    div[data-testid="stExpander"] details {
        background: transparent !important;
        border: none !important;
    }
    div[data-testid="stExpander"] summary {
        background: #1A1C1E !important;
        border: none !important;
        color: #ECEBE6 !important;
        font-size: 13px !important;
        font-weight: 500 !important;
        padding: 12px 18px !important;
        cursor: pointer !important;
        display: flex !important;
        align-items: center !important;
        justify-content: space-between !important;
        transition: background-color 0.15s ease, color 0.15s ease !important;
        list-style: none !important;
    }
    div[data-testid="stExpander"] summary::-webkit-details-marker {
        display: none !important;
    }
    div[data-testid="stExpander"] summary:hover {
        background: #202225 !important;
        color: #FFFFFF !important;
    }
    div[data-testid="stExpander"] summary svg {
        display: inline-block !important;
        width: 16px !important;
        height: 16px !important;
        color: #9A9C98 !important;
        transition: transform 0.25s cubic-bezier(0.165, 0.84, 0.44, 1), color 0.2s ease !important;
    }
    div[data-testid="stExpander"] details[open] summary svg {
        transform: rotate(180deg) !important;
        color: #C8F169 !important;
    }
    div[data-testid="stExpanderDetails"] {
        border-top: 0.5px solid #2A2D30 !important;
        padding: 16px !important;
        margin-top: 0 !important;
        background: #141517 !important;
    }

    /* SECTION 3: FILTER TILES (Grid) */
    .filter-tiles-grid {
        display: grid;
        grid-template-columns: repeat(5, 1fr) 1.25fr;
        gap: 12px;
        margin-bottom: 24px;
        align-items: stretch;
    }
    .filter-tiles-grid.views-expanded {
        grid-template-columns: repeat(5, 0.88fr) 1.6fr;
    }
    @media (max-width: 1200px) {
        .filter-tiles-grid.views-expanded {
            grid-template-columns: repeat(5, 0.82fr) 1.9fr;
        }
    }
    @media (max-width: 1000px) {
        .filter-tiles-grid, .filter-tiles-grid.views-expanded {
            grid-template-columns: repeat(3, 1fr);
        }
    }
    @media (max-width: 680px) {
        .filter-tiles-grid, .filter-tiles-grid.views-expanded {
            grid-template-columns: repeat(2, 1fr);
        }
    }

    .tile-card, a.tile-card {
        background: #1A1C1E;
        border: 1px solid #2A2D30;
        border-radius: 14px;
        padding: 16px 18px;
        min-height: 135px;
        height: auto;
        display: flex;
        flex-direction: column;
        justify-content: space-between;
        text-align: left;
        text-decoration: none !important;
        transition: border-color 0.15s ease, background-color 0.15s ease;
        cursor: pointer;
        user-select: none;
        box-sizing: border-box;
    }
    .tile-card:hover, a.tile-card:hover {
        border-color: #3A3E42;
        text-decoration: none !important;
    }
    .tile-card.active, a.tile-card.active {
        background: #C8F169 !important;
        border-color: #C8F169 !important;
        text-decoration: none !important;
    }
    .tile-label {
        font-size: 13px;
        font-weight: 500;
        color: #9A9C98;
        line-height: 1.2;
    }
    .tile-card.active .tile-label, a.tile-card.active .tile-label {
        color: #3B4A14 !important;
    }
    .tile-num {
        font-family: 'JetBrains Mono', monospace;
        font-size: 38px;
        font-weight: 600;
        letter-spacing: -0.02em;
        color: #ECEBE6;
        line-height: 1.1;
        margin-top: 4px;
    }
    .tile-card.active .tile-num, a.tile-card.active .tile-num {
        color: #121314 !important;
    }
    .tile-subtext {
        font-size: 12px;
        color: #9A9C98;
        line-height: 1.2;
    }
    .tile-card.active .tile-subtext, a.tile-card.active .tile-subtext {
        color: #3B4A14 !important;
    }

    /* Tile 6: Views special layout */
    .views-tile-body {
        display: flex;
        flex-direction: column;
        justify-content: space-between;
        height: 100%;
    }
    .views-tile-top {
        display: flex;
        flex-direction: column;
        gap: 2px;
    }
    .views-tile-num {
        font-family: 'JetBrains Mono', monospace;
        font-size: 28px;
        font-weight: 600;
        letter-spacing: -0.02em;
        color: #ECEBE6;
        line-height: 1.15;
        white-space: nowrap;
        overflow: hidden;
        text-overflow: ellipsis;
    }
    .tile-card.active .views-tile-num, a.tile-card.active .views-tile-num {
        color: #121314 !important;
    }
    .views-tile-sub {
        font-size: 12px;
        color: #ECEBE6;
        line-height: 1.2;
        white-space: nowrap;
    }
    .tile-card.active .views-tile-sub, a.tile-card.active .views-tile-sub {
        color: #121314 !important;
    }
    .views-tile-divider {
        height: 1px;
        background: #2A2D30;
        margin: 4px 0;
    }
    .tile-card.active .views-tile-divider, a.tile-card.active .views-tile-divider {
        background: #3B4A14 !important;
    }
    .views-tile-bottom {
        font-size: 11px;
        color: #9A9C98;
        line-height: 1.25;
        white-space: normal;
    }
    .tile-card.active .views-tile-bottom, a.tile-card.active .views-tile-bottom {
        color: #3B4A14 !important;
    }

    /* SECTION 4: RESULTS SECTION */
    .results-header-bar {
        display: flex;
        justify-content: space-between;
        align-items: flex-end;
        flex-wrap: wrap;
        gap: 16px;
        margin-top: 4px;
        margin-bottom: 16px;
    }
    .results-header-left {
        display: flex;
        flex-direction: column;
        gap: 6px;
        flex: 1 1 520px;
        min-width: 0;
    }
    .results-header-actions {
        display: flex;
        align-items: center;
        gap: 12px;
        flex-shrink: 0;
    }
    .results-meta-line {
        font-size: 13px;
        font-weight: 400;
        color: #9A9C98;
        display: flex;
        align-items: center;
        flex-wrap: wrap;
        gap: 8px;
    }
    .meta-tooltip-pill {
        background: #1A1C1E;
        border: 1px solid #2A2D30;
        border-radius: 999px;
        padding: 2px 8px;
        font-size: 11px;
        color: #9A9C98;
        cursor: help;
        user-select: none;
        transition: color 0.15s ease, border-color 0.15s ease;
    }
    .meta-tooltip-pill:hover {
        color: #ECEBE6;
        border-color: #3A3E42;
    }
    .promo-sub-tabs {
        display: flex;
        gap: 8px;
        margin-bottom: 14px;
        flex-wrap: wrap;
    }
    .promo-sub-tab {
        background: #1A1C1E;
        border: 1px solid #2A2D30;
        border-radius: 999px;
        padding: 6px 14px;
        font-size: 12px;
        font-weight: 500;
        color: #9A9C98;
        text-decoration: none !important;
        transition: all 0.15s ease;
    }
    .promo-sub-tab:hover {
        color: #ECEBE6;
        border-color: #3A3E42;
    }
    .promo-sub-tab.active {
        background: #C8F169;
        border-color: #C8F169;
        color: #121314;
        font-weight: 600;
    }


    /* Anchored Copy Toast Notification directly on Copy Button */
    .copy-btn-anchor-wrapper {
        position: relative;
        display: inline-flex;
        align-items: center;
    }
    .copy-button-toast-anchor {
        position: absolute;
        bottom: calc(100% + 8px);
        left: 50%;
        transform: translateX(-50%);
        display: flex;
        flex-direction: column-reverse;
        align-items: center;
        gap: 6px;
        pointer-events: none;
        z-index: 99999999;
        white-space: nowrap;
    }
    .adwhisper-toast-pill {
        position: relative;
        background: #1A1C1E;
        border: 1px solid #C8F169;
        color: #ECEBE6;
        font-family: 'Inter Tight', -apple-system, BlinkMacSystemFont, sans-serif;
        font-size: 12px;
        font-weight: 600;
        padding: 6px 14px;
        border-radius: 16px;
        box-shadow: 0 4px 20px rgba(0, 0, 0, 0.85), 0 0 14px rgba(200, 241, 105, 0.35);
        display: inline-flex;
        align-items: center;
        gap: 6px;
        white-space: nowrap;
        user-select: none;
        pointer-events: none;
        animation: toastAnchorFloatFade 1.4s cubic-bezier(0.16, 1, 0.3, 1) forwards;
    }
    .adwhisper-toast-pill::after {
        content: '';
        position: absolute;
        bottom: -5px;
        left: 50%;
        transform: translateX(-50%);
        border-width: 5px 5px 0 5px;
        border-style: solid;
        border-color: #1A1C1E transparent transparent transparent;
    }
    @keyframes toastAnchorFloatFade {
        0% {
            opacity: 0;
            transform: translateY(6px) scale(0.88);
        }
        14% {
            opacity: 1;
            transform: translateY(0) scale(1);
        }
        60% {
            opacity: 1;
            transform: translateY(0) scale(1);
        }
        100% {
            opacity: 0;
            transform: translateY(-22px) scale(0.92);
        }
    }

    /* Promo Variant Pills (native instant switching without disconnect) */
    .st-key-promo_variant_pills {
        margin-bottom: 14px;
    }
    .st-key-promo_variant_pills div[data-testid="stButtonGroup"] {
        display: flex;
        gap: 8px;
        flex-wrap: wrap;
    }
    .st-key-promo_variant_pills button[data-variant="pills"] {
        background: #1A1C1E !important;
        border: 1px solid #2A2D30 !important;
        border-radius: 999px !important;
        padding: 6px 14px !important;
        font-size: 12px !important;
        font-weight: 500 !important;
        color: #9A9C98 !important;
        transition: all 0.15s ease !important;
        min-height: 0 !important;
        height: auto !important;
        box-shadow: none !important;
    }
    .st-key-promo_variant_pills button[data-variant="pills"]:hover {
        color: #ECEBE6 !important;
        border-color: #3A3E42 !important;
        background: #232528 !important;
    }
    .st-key-promo_variant_pills button[data-variant="pills"][data-selected="true"],
    .st-key-promo_variant_pills button[data-variant="pills"][aria-checked="true"] {
        background: #C8F169 !important;
        border-color: #C8F169 !important;
        color: #121314 !important;
        font-weight: 600 !important;
    }
    .st-key-promo_variant_pills button[data-variant="pills"] p {
        font-size: 12px !important;
        margin: 0 !important;
        line-height: 1.4 !important;
        color: inherit !important;
    }
    .st-key-promo_variant_pills button[data-variant="pills"][data-selected="true"] p,
    .st-key-promo_variant_pills button[data-variant="pills"][aria-checked="true"] p {
        color: #121314 !important;
        font-weight: 600 !important;
    }
    .results-pill-filter {
        background: #1A1C1E;
        border: 1px solid #2A2D30;
        border-radius: 999px;
        padding: 3px 10px;
        font-size: 12px;
        color: #ECEBE6;
        cursor: pointer;
        text-decoration: none;
        transition: border-color 0.15s ease;
    }
    .results-pill-filter:hover {
        border-color: #3A3E42;
    }
    .results-pill-filter.active {
        border-color: #C8F169;
        color: #C8F169;
    }
    .results-title-h1 {
        font-size: 28px;
        font-weight: 600;
        letter-spacing: -0.02em;
        color: #ECEBE6;
        line-height: 1.2;
        margin: 0;
    }
    @media (max-width: 768px) {
        .results-header-bar {
            flex-direction: column;
            align-items: flex-start;
            gap: 14px;
        }
        .results-header-actions {
            width: 100%;
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 10px;
        }
    }
    @media (max-width: 480px) {
        .results-header-actions {
            grid-template-columns: 1fr;
        }
        .results-title-h1 {
            font-size: 20px !important;
        }
    }

    /* Table Container */
    .table-card {
        background: #1A1C1E;
        border: 1px solid #2A2D30;
        border-radius: 16px;
        overflow-x: auto;
        margin-bottom: 24px;
    }
    table.spec-table {
        width: 100%;
        border-collapse: collapse;
        font-size: 14px;
        text-align: left;
    }
    table.spec-table th {
        font-size: 12px;
        font-weight: 500;
        color: #9A9C98;
        padding: 12px 10px;
        border-bottom: 1px solid #2A2D30;
        background: #1A1C1E;
        user-select: none;
    }
    table.spec-table td {
        padding: 12px 10px;
        border-bottom: 1px solid #2A2D30;
        color: #ECEBE6;
        vertical-align: middle;
    }
    table.spec-table tr:last-child td {
        border-bottom: none;
    }
    table.spec-table tr:hover td {
        background: rgba(255, 255, 255, 0.015);
    }
    a.td-id-link {
        font-family: 'JetBrains Mono', monospace !important;
        font-size: 13px !important;
        color: #ECEBE6 !important;
        text-decoration: none !important;
        white-space: nowrap !important;
        transition: color 0.15s ease !important;
    }
    a.td-id-link:hover {
        color: #C8F169 !important;
        text-decoration: underline !important;
    }
    .th-num, .td-num {
        font-family: 'JetBrains Mono', monospace;
        font-size: 13px;
        color: #9A9C98;
        text-align: center !important;
        width: 48px;
        white-space: nowrap;
    }
    .td-id {
        font-family: 'JetBrains Mono', monospace;
        font-size: 13px;
        white-space: nowrap;
        color: #ECEBE6;
    }
    .th-views, .td-views {
        font-family: 'JetBrains Mono', monospace;
        font-size: 13px;
        text-align: right !important;
        color: #ECEBE6;
        white-space: nowrap;
        width: 90px;
    }
    .td-muted {
        font-family: 'JetBrains Mono', monospace;
        font-size: 13px;
        color: #9A9C98;
        white-space: nowrap;
    }
    .th-timecode, .td-timecode {
        font-family: 'JetBrains Mono', monospace;
        font-size: 13px;
        color: #9A9C98;
        text-align: center !important;
        white-space: nowrap;
        width: 105px;
    }
    .th-conf, .td-conf {
        font-family: 'JetBrains Mono', monospace;
        font-size: 13px;
        color: #ECEBE6;
        white-space: nowrap;
        text-align: center !important;
        width: 110px;
    }
    .td-transcript {
        font-size: 13px;
        color: #ECEBE6;
        max-width: 440px;
        line-height: 1.4;
    }
    .td-audio {
        text-align: center;
        width: 60px;
    }

    /* Highlighted matched phrase and expandable transcript */
    details.tbl-trans-details {
        cursor: pointer;
    }
    summary.tbl-trans-summary {
        list-style: none;
        outline: none;
        font-size: 13px;
        color: #ECEBE6;
        line-height: 1.4;
        user-select: text;
    }
    summary.tbl-trans-summary::-webkit-details-marker {
        display: none;
    }
    mark.hl-phrase {
        background: rgba(200, 241, 105, 0.18);
        color: #C8F169;
        padding: 1px 4px;
        border-radius: 4px;
        font-weight: 600;
    }
    .tbl-trans-full {
        margin-top: 8px;
        padding: 8px 12px;
        background: #121314;
        border: 1px solid #2A2D30;
        border-radius: 6px;
        font-size: 12px;
        color: #CFCEC8;
        line-height: 1.4;
        max-height: 180px;
        overflow-y: auto;
        white-space: normal;
    }

    /* Round Play Button 36px */
    .play-round-btn {
        width: 36px;
        height: 36px;
        border-radius: 50%;
        background: #1A1C1E;
        border: 1px solid #3A3E42;
        color: #ECEBE6;
        display: inline-flex;
        align-items: center;
        justify-content: center;
        cursor: pointer;
        transition: all 0.15s ease;
    }
    .play-round-btn:hover {
        border-color: #C8F169;
        color: #C8F169;
    }
    .play-round-btn.is-playing {
        background: #C8F169;
        border-color: #C8F169;
        color: #121314;
    }

    /* SECTION 5: PUBLICATION CARDS (<details>) */
    details.outer-cards-details {
        background: #121314;
        border: 1px solid #2A2D30;
        border-radius: 16px;
        margin-bottom: 24px;
        overflow: hidden;
    }
    summary.outer-summary {
        list-style: none;
        cursor: pointer;
        padding: 18px 24px;
        display: flex;
        align-items: center;
        gap: 10px;
        user-select: none;
    }
    summary.outer-summary::-webkit-details-marker {
        display: none;
    }
    .outer-summary-title {
        font-size: 16px;
        font-weight: 600;
        color: #ECEBE6;
    }
    .outer-summary-count {
        font-size: 14px;
        color: #9A9C98;
    }
    .outer-cards-content {
        padding: 0 16px 16px 16px;
        display: flex;
        flex-direction: column;
        gap: 10px;
    }

    /* Individual Card */
    details.card-details {
        background: #1A1C1E;
        border: 1px solid #2A2D30;
        border-radius: 14px;
        overflow: hidden;
    }
    summary.card-summary {
        list-style: none;
        cursor: pointer;
        padding: 16px 20px;
        display: flex;
        align-items: center;
        gap: 12px;
        user-select: none;
    }
    summary.card-summary::-webkit-details-marker {
        display: none;
    }
    .card-num-badge {
        font-family: 'JetBrains Mono', monospace;
        font-size: 13px;
        font-weight: 600;
        color: #9A9C98;
        background: #202225;
        border: 1px solid #2A2D30;
        border-radius: 6px;
        padding: 2px 7px;
        display: inline-flex;
        align-items: center;
        justify-content: center;
        line-height: 1.2;
        flex-shrink: 0;
    }
    .card-variant-title {
        font-size: 15px;
        font-weight: 600;
        color: #ECEBE6;
    }
    .card-pill-tag {
        font-size: 12px;
        color: #C8F169;
        border: 1px solid #3B4A14;
        border-radius: 999px;
        padding: 2px 10px;
        font-weight: 500;
    }
    .card-views-txt {
        font-size: 14px;
        color: #ECEBE6;
    }
    .card-meta-muted {
        font-family: 'JetBrains Mono', monospace;
        font-size: 13px;
        color: #9A9C98;
    }

    /* Chevron rotation */
    .chevron-icon {
        transition: transform 0.2s ease;
        display: inline-flex;
        color: #9A9C98;
    }
    details[open] > summary .chevron-icon {
        transform: rotate(90deg);
    }

    /* Expanded Card Body */
    .card-expanded-body {
        border-top: 1px solid #2A2D30;
        padding: 20px;
        display: flex;
        gap: 24px;
    }
    @media (max-width: 900px) {
        .card-expanded-body {
            flex-direction: column;
        }
    }
    .card-col-left {
        flex: 1;
        display: flex;
        flex-direction: column;
        gap: 12px;
    }
    .card-col-right {
        width: 340px;
        display: flex;
        flex-direction: column;
        gap: 12px;
    }
    @media (max-width: 900px) {
        .card-col-right {
            width: 100%;
        }
    }

    .card-tiktok-link {
        font-family: 'JetBrains Mono', monospace;
        font-size: 14px;
        color: #C8F169;
        text-decoration: underline;
        word-break: break-all;
    }
    .card-stat-row {
        display: flex;
        align-items: center;
        gap: 24px;
        flex-wrap: wrap;
    }
    .card-stat-item {
        display: flex;
        flex-direction: column;
        gap: 2px;
    }
    .card-transcript-box {
        background: #121314;
        border: 1px solid #2A2D30;
        border-radius: 10px;
        padding: 16px 18px;
        font-size: 16px;
        line-height: 1.5;
        color: #ECEBE6;
    }

    /* Player Pill 56px */
    .player-pill {
        background: #121314;
        border: 1px solid #2A2D30;
        border-radius: 999px;
        height: 56px;
        padding: 6px 16px;
        display: flex;
        align-items: center;
        gap: 12px;
    }
    .player-play-btn {
        width: 44px;
        height: 44px;
        border-radius: 50%;
        background: #ECEBE6;
        border: none;
        color: #121314;
        display: inline-flex;
        align-items: center;
        justify-content: center;
        cursor: pointer;
        flex-shrink: 0;
    }
    .player-play-btn:hover {
        background: #FFFFFF;
    }
    .player-track {
        flex: 1;
        height: 4px;
        background: #2A2D30;
        border-radius: 2px;
        position: relative;
        overflow: hidden;
    }
    .player-track-fill {
        height: 100%;
        background: #C8F169;
        width: 0%;
        transition: width 0.1s linear;
    }
    .player-time {
        font-family: 'JetBrains Mono', monospace;
        font-size: 12px;
        color: #9A9C98;
        white-space: nowrap;
    }

    /* Demucs button */
    .demucs-btn-card {
        height: 44px;
        background: #1A1C1E;
        border: 1px solid #2A2D30;
        border-radius: 10px;
        color: #ECEBE6;
        font-family: 'Inter Tight', sans-serif;
        font-size: 14px;
        font-weight: 500;
        width: 100%;
        cursor: pointer;
        display: flex;
        align-items: center;
        justify-content: center;
        text-decoration: none !important;
        transition: all 0.15s ease;
    }
    .demucs-btn-card:hover {
        border-color: #C8F169;
        color: #C8F169;
        text-decoration: none !important;
    }

    /* Action bar Copy & Download buttons */
    .action-btn-copy {
        height: 44px;
        background: #ECEBE6;
        border: none;
        border-radius: 10px;
        color: #121314;
        font-family: 'Inter Tight', sans-serif;
        font-size: 14px;
        font-weight: 600;
        padding: 0 18px;
        cursor: pointer;
        display: inline-flex;
        align-items: center;
        justify-content: center;
        text-decoration: none;
        white-space: nowrap;
        min-width: 195px;
        box-sizing: border-box;
    }
    .action-btn-copy:hover {
        background: #FFFFFF;
    }
    .action-btn-outline {
        height: 44px;
        background: #1A1C1E;
        border: 1px solid #2A2D30;
        border-radius: 10px;
        color: #ECEBE6;
        font-family: 'Inter Tight', sans-serif;
        font-size: 14px;
        font-weight: 500;
        padding: 0 18px;
        cursor: pointer;
        display: inline-flex;
        align-items: center;
        justify-content: center;
        text-decoration: none;
    }
    .action-btn-outline:hover {
        border-color: #3A3E42;
        color: #FFFFFF;
    }

    /* EXTRA SOURCES & DATABASE BLOCK (Mockup Alignment) */
    .extra-sources-container div[data-testid="stHorizontalBlock"],
    div[data-testid="stExpander"] div[data-testid="stHorizontalBlock"] {
        display: grid !important;
        grid-template-columns: repeat(4, minmax(0, 1fr)) !important;
        gap: 16px !important;
        align-items: stretch !important;
    }

    @media (max-width: 1100px) {
        .extra-sources-container div[data-testid="stHorizontalBlock"],
        div[data-testid="stExpander"] div[data-testid="stHorizontalBlock"] {
            grid-template-columns: repeat(2, minmax(0, 1fr)) !important;
        }
    }

    @media (max-width: 640px) {
        .extra-sources-container div[data-testid="stHorizontalBlock"],
        div[data-testid="stExpander"] div[data-testid="stHorizontalBlock"] {
            grid-template-columns: 1fr !important;
        }
    }

    .extra-sources-container div[data-testid="stColumn"],
    div[data-testid="stExpander"] div[data-testid="stColumn"] {
        width: 100% !important;
        background: #1A1C1E !important;
        border: 0.5px solid #2A2D30 !important;
        border-radius: 12px !important;
        padding: 16px !important;
        display: flex !important;
        flex-direction: column !important;
        gap: 10px !important;
        box-sizing: border-box !important;
        transition: border-color 0.2s ease !important;
    }

    .extra-sources-container div[data-testid="stColumn"]:hover,
    div[data-testid="stExpander"] div[data-testid="stColumn"]:hover {
        border-color: #3A3E42 !important;
    }

    .bs-t {
        font-size: 11px !important;
        letter-spacing: .06em !important;
        text-transform: uppercase !important;
        color: #9A9C98 !important;
        font-weight: 500 !important;
        margin-bottom: 2px !important;
    }

    .bs-row {
        display: flex !important;
        justify-content: space-between !important;
        font-size: 12px !important;
        color: #9A9C98 !important;
        align-items: center !important;
    }

    .bs-row b {
        font-weight: 500 !important;
        color: #ECEBE6 !important;
    }

    .bs-badge {
        display: inline-flex !important;
        align-items: center !important;
        gap: 6px !important;
        font-size: 12px !important;
        color: #C8F169 !important;
        font-weight: 500 !important;
    }

    .bs-dot {
        width: 7px !important;
        height: 7px !important;
        border-radius: 50% !important;
        background: #C8F169 !important;
        display: inline-block !important;
    }

    .extra-sources-container textarea {
        width: 100% !important;
        min-height: 72px !important;
        max-height: 140px !important;
        resize: vertical !important;
        font-size: 12px !important;
        background: #121314 !important;
        border: 0.5px solid #2A2D30 !important;
        border-radius: 8px !important;
        color: #F1F5F9 !important;
        font-family: 'JetBrains Mono', monospace !important;
        box-sizing: border-box !important;
        padding: 8px 10px !important;
    }

    .extra-sources-container textarea::placeholder {
        font-style: italic !important;
        color: #5A5D62 !important;
    }

    .extra-sources-container div[data-testid="stFileUploader"] {
        margin-top: 0 !important;
    }

    /* Clean Dashed Dropzone */
    [data-testid="stFileUploaderDropzone"] {
        background-color: #121314 !important;
        border: 1px dashed #3A3E42 !important;
        border-radius: 8px !important;
        padding: 20px 12px !important;
        text-align: center !important;
        transition: border-color 0.2s ease, background-color 0.2s ease !important;
        display: flex !important;
        flex-direction: column !important;
        align-items: center !important;
        justify-content: center !important;
        cursor: pointer !important;
    }

    [data-testid="stFileUploaderDropzone"]:hover {
        border-color: #C8F169 !important;
        background-color: #16181A !important;
    }

    [data-testid="stFileUploaderDropzone"] button,
    [data-testid="stFileUploaderDropzone"] span:has(button) {
        display: none !important;
    }

    [data-testid="stFileUploaderDropzoneInstructions"] {
        width: 100% !important;
        text-align: center !important;
        margin: 0 !important;
    }

    [data-testid="stFileUploaderDropzoneInstructions"] span {
        font-size: 0 !important;
        display: block !important;
        text-align: center !important;
        line-height: 1.4 !important;
    }

    [data-testid="stFileUploaderDropzoneInstructions"] span::before {
        content: "↑ Перетащите файлы или нажмите" !important;
        font-size: 12px !important;
        color: #ECEBE6 !important;
        font-weight: 500 !important;
        display: block !important;
        margin-bottom: 3px !important;
    }

    [data-testid="stFileUploaderDropzoneInstructions"] span::after {
        content: "MP3, WAV, M4A, OGG · до 200 МБ на файл" !important;
        font-size: 11px !important;
        color: #9A9C98 !important;
        display: block !important;
    }

    div[data-testid="stExpander"] [data-testid="stColumn"]:nth-child(2) [data-testid="stFileUploaderDropzoneInstructions"] span::after {
        content: "cookies.txt (Netscape) · до 200 МБ" !important;
    }

    /* Danger Button in Card 4 */
    div[data-testid="stExpander"] div[data-testid="stColumn"]:nth-child(4) div.stButton:last-of-type button {
        border: 0.5px solid #D03B3B !important;
        color: #D03B3B !important;
        background: transparent !important;
        font-size: 13px !important;
        height: 36px !important;
        border-radius: 8px !important;
        display: flex !important;
        align-items: center !important;
        justify-content: center !important;
        gap: 6px !important;
        transition: all 0.2s ease !important;
    }

    div[data-testid="stExpander"] div[data-testid="stColumn"]:nth-child(4) div.stButton:last-of-type button:hover {
        background: rgba(208, 59, 59, 0.12) !important;
        border-color: #E34948 !important;
        color: #E34948 !important;
    }

    /* Secondary Ghost Buttons in Advanced Expander */
    div[data-testid="stExpander"] div[data-testid="stColumn"] button[data-testid="baseButton-secondary"],
    div[data-testid="stExpander"] div[data-testid="stColumn"] button[data-testid="stBaseButton-secondary"] {
        background: transparent !important;
        border: 0.5px solid #2A2D30 !important;
        color: #ECEBE6 !important;
        font-size: 13px !important;
        border-radius: 8px !important;
        transition: all 0.2s ease !important;
    }
    div[data-testid="stExpander"] div[data-testid="stColumn"] button[data-testid="baseButton-secondary"]:hover,
    div[data-testid="stExpander"] div[data-testid="stColumn"] button[data-testid="stBaseButton-secondary"]:hover {
        border-color: #C8F169 !important;
        color: #C8F169 !important;
        background: rgba(200, 241, 105, 0.05) !important;
    }

    /* Dialog styling */
    div[data-testid="stDialog"] div[role="dialog"] {
        background: #1A1C1E !important;
        border: 0.5px solid #2A2D30 !important;
        border-radius: 12px !important;
        padding: 24px !important;
        box-shadow: 0 16px 48px rgba(0, 0, 0, 0.7) !important;
        max-width: 420px !important;
    }
    div[data-testid="stDialog"] h2 {
        color: #ECEBE6 !important;
        font-size: 16px !important;
    }
    div[data-testid="stDialog"] [data-testid="stColumn"]:last-child button {
        background-color: #D03B3B !important;
        border: 0.5px solid #D03B3B !important;
        color: #FFFFFF !important;
        font-weight: 500 !important;
        transition: all 0.2s ease !important;
    }
    div[data-testid="stDialog"] [data-testid="stColumn"]:last-child button:hover:not(:disabled) {
        background-color: #E34948 !important;
        border-color: #E34948 !important;
    }
    div[data-testid="stDialog"] [data-testid="stColumn"]:last-child button:disabled {
        background-color: #232528 !important;
        border-color: #2A2D30 !important;
        color: #5A5D62 !important;
        cursor: not-allowed !important;
        opacity: 0.6 !important;
    }
</style>
""", unsafe_allow_html=True)

import streamlit.components.v1 as components
components.html("""
<script>
(function(){
    var w = (window.parent && window.parent.document) ? window.parent : window;
    var prev = w.document.getElementById("adwhisper_injected_script");
    if (prev && prev.parentNode) prev.parentNode.removeChild(prev);

    var s = w.document.createElement("script");
    s.id = "adwhisper_injected_script";
    s.textContent = `
        window.__currentAudio = null;
        window.__currentBtn = null;

        window.updatePlayIcon = function(btnEl, isPlaying) {
            if (!btnEl) return;
            var isSmall = btnEl.classList.contains('play-round-btn');
            var size = isSmall ? 14 : 16;
            var playSvg = '<svg width="' + size + '" height="' + size + '" viewBox="0 0 24 24" fill="currentColor"><polygon points="6 4 20 12 6 20 6 4"></polygon></svg>';
            var pauseSvg = '<svg width="' + size + '" height="' + size + '" viewBox="0 0 24 24" fill="currentColor"><rect x="6" y="4" width="4" height="16"></rect><rect x="14" y="4" width="4" height="16"></rect></svg>';
            btnEl.innerHTML = isPlaying ? pauseSvg : playSvg;
        };

        window.bsInitCardTrack = function(audioId, fillId, timeId) {
            var audio = document.getElementById(audioId);
            var fill = document.getElementById(fillId);
            var timeEl = document.getElementById(timeId);
            if (!audio) return;

            function updateTime() {
                if (!audio.duration || isNaN(audio.duration)) return;
                var pct = Math.min(100, Math.max(0, (audio.currentTime / audio.duration) * 100));
                if (fill) fill.style.width = pct + '%';
                if (timeEl) {
                    var curM = Math.floor(audio.currentTime / 60);
                    var curS = Math.floor(audio.currentTime % 60).toString().padStart(2, '0');
                    var durM = Math.floor(audio.duration / 60);
                    var durS = Math.floor(audio.duration % 60).toString().padStart(2, '0');
                    timeEl.textContent = curM + ':' + curS + ' / ' + durM + ':' + durS;
                }
            }

            audio.ontimeupdate = updateTime;
            audio.onloadedmetadata = updateTime;
        };

        window.bsToggleAudio = function(audioId, btnEl) {
            var audio = document.getElementById(audioId);
            if (!audio) return;

            if (audio.__playPending) return;

            if (window.__currentAudio === audio && !audio.paused) {
                audio.pause();
                btnEl.classList.remove('is-playing');
                window.updatePlayIcon(btnEl, false);
                return;
            }

            if (window.__currentAudio && window.__currentAudio !== audio) {
                try {
                    window.__currentAudio.pause();
                } catch(e) {}
                if (window.__currentBtn) {
                    window.__currentBtn.classList.remove('is-playing');
                    window.updatePlayIcon(window.__currentBtn, false);
                }
            }

            window.__currentAudio = audio;
            window.__currentBtn = btnEl;

            audio.onended = function(){
                btnEl.classList.remove('is-playing');
                window.updatePlayIcon(btnEl, false);
                var fillId = btnEl.getAttribute('data-fill-id');
                var timeId = btnEl.getAttribute('data-time-id');
                if (fillId) {
                    var f = document.getElementById(fillId);
                    if (f) f.style.width = '0%';
                }
                if (timeId && audio.duration) {
                    var t = document.getElementById(timeId);
                    var durM = Math.floor(audio.duration / 60);
                    var durS = Math.floor(audio.duration % 60).toString().padStart(2, '0');
                    if (t) t.textContent = '0:00 / ' + durM + ':' + durS;
                }
            };

            audio.onpause = function(){
                btnEl.classList.remove('is-playing');
                window.updatePlayIcon(btnEl, false);
            };

            audio.onplay = function(){
                btnEl.classList.add('is-playing');
                window.updatePlayIcon(btnEl, true);
            };

            audio.__playPending = true;
            var playPromise = audio.play();
            if (playPromise !== undefined) {
                playPromise.then(function(){
                    audio.__playPending = false;
                    btnEl.classList.add('is-playing');
                    window.updatePlayIcon(btnEl, true);
                }).catch(function(e){
                    audio.__playPending = false;
                    console.warn('Audio play error:', e);
                    btnEl.classList.remove('is-playing');
                    window.updatePlayIcon(btnEl, false);
                });
            } else {
                audio.__playPending = false;
                btnEl.classList.add('is-playing');
                window.updatePlayIcon(btnEl, true);
            }
        };

        function execCommandCopySync(text) {
            var ta = document.createElement("textarea");
            ta.value = text;
            ta.setAttribute("readonly", "");
            ta.style.position = "fixed";
            ta.style.top = "0";
            ta.style.left = "0";
            ta.style.width = "2em";
            ta.style.height = "2em";
            ta.style.padding = "0";
            ta.style.border = "none";
            ta.style.outline = "none";
            ta.style.boxShadow = "none";
            ta.style.background = "transparent";
            ta.style.opacity = "0.01";
            ta.style.zIndex = "-99999";
            ta.setAttribute("aria-hidden", "true");
            document.body.appendChild(ta);
            
            var ok = false;
            try {
                ta.removeAttribute("readonly");
                ta.focus({ preventScroll: true });
                ta.select();
                ta.setSelectionRange(0, ta.value.length);
                ok = document.execCommand("copy");
            } catch (err) {
                ok = false;
            } finally {
                if (ta.parentNode) {
                    document.body.removeChild(ta);
                }
            }
            return ok;
        }

        function copyTextEverywhere(text) {
            if (!text) return false;
            var ok = execCommandCopySync(text);
            try {
                if (window.navigator && window.navigator.clipboard && typeof window.navigator.clipboard.writeText === "function") {
                    window.navigator.clipboard.writeText(text).catch(function(){});
                }
            } catch(e) {}
            return ok;
        }

        function showCopyToast(count, btnEl) {
            var btn = btnEl || document.getElementById("copy_links_btn_main");
            var container = document.getElementById("adwhisper_copy_toast_anchor");
            if (!container && btn) {
                var parent = btn.closest(".copy-btn-anchor-wrapper") || btn.parentNode;
                container = parent ? parent.querySelector(".copy-button-toast-anchor") : null;
                if (!container && parent) {
                    container = document.createElement("div");
                    container.id = "adwhisper_copy_toast_anchor";
                    container.className = "copy-button-toast-anchor";
                    parent.appendChild(container);
                }
            }
            if (!container) container = document.body;

            var existing = container.querySelectorAll(".adwhisper-toast-pill");
            if (existing.length >= 2) {
                for (var j = 0; j < existing.length - 1; j++) {
                    var old = existing[j];
                    old.style.transition = "all 0.2s cubic-bezier(0.16, 1, 0.3, 1)";
                    old.style.opacity = "0";
                    old.style.transform = "translateY(-30px) scale(0.82)";
                    setTimeout((function(el) { return function() { if (el && el.parentNode) el.parentNode.removeChild(el); }; })(old), 200);
                }
            }
            
            var pill = document.createElement("div");
            pill.className = "adwhisper-toast-pill";
            if (!count || count === "0") {
                pill.innerHTML = '<span>Нет ссылок для копирования</span>';
            } else {
                var countText = count ? (" (" + count + ")") : "";
                pill.innerHTML = '<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="#C8F169" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"></polyline></svg><span>Скопировано' + countText + '</span>';
            }
            container.appendChild(pill);
            
            setTimeout(function() {
                if (pill && pill.parentNode) {
                    pill.parentNode.removeChild(pill);
                }
            }, 1400);
        }

        window.bsHandleCopyClick = function(btn) {
            if (!btn) return;
            if (btn.__lastCopyTime && (Date.now() - btn.__lastCopyTime < 50)) return;
            btn.__lastCopyTime = Date.now();

            var textToCopy = btn.getAttribute("data-plain-text") || "";
            if (!textToCopy) {
                try {
                    var raw = btn.getAttribute("data-links");
                    var links = JSON.parse(raw || "[]");
                    textToCopy = Array.isArray(links) ? links.join(String.fromCharCode(10)) : String(raw || "");
                } catch(e) {
                    textToCopy = "";
                }
            }
            if (!textToCopy) {
                var domLinks = [];
                document.querySelectorAll(".results-table a[href*='tiktok.com'], .table-card a[href*='tiktok.com']").forEach(function(a) {
                    var href = a.getAttribute("href");
                    if (href && domLinks.indexOf(href) === -1) domLinks.push(href);
                });
                if (domLinks.length > 0) textToCopy = domLinks.join(String.fromCharCode(10));
            }

            var count = btn.getAttribute("data-count") || "";
            if (!textToCopy || count === "0") {
                showCopyToast("0", btn);
                return;
            }

            copyTextEverywhere(textToCopy);

            var origText = "Скопировать ссылки" + (count ? " (" + count + ")" : "");
            btn.innerText = "Скопировано ✓";
            showCopyToast(count, btn);
            
            clearTimeout(btn.__resetTimeout);
            btn.__resetTimeout = setTimeout(function() {
                if (btn) btn.innerText = origText;
            }, 1400);
        };

        // Capture-phase click listener for copy links button
        if (!window.__copy_btn_bound) {
            window.__copy_btn_bound = true;
            document.addEventListener("click", function(e) {
                var btn = e.target.closest("#copy_links_btn_main");
                if (btn) {
                    e.preventDefault();
                    e.stopImmediatePropagation();
                    window.bsHandleCopyClick(btn);
                }
            }, true);
        }

        // Capture-phase listener for top tile cards: instant in-place switch without full-screen spinner
        var tileToLabelKeyword = {
            "keyser": "caser",
            "upgrade": "upgrader",
            "dotagrade": "dotagrade",
            "all_promo": "все рекламные"
        };

        if (!window.__tile_card_bound) {
            window.__tile_card_bound = true;
            document.addEventListener("click", function(e) {
                var card = e.target.closest(".tile-card");
                if (!card) return;
                
                var tile = card.getAttribute("data-tile");
                if (!tile) {
                    var href = card.getAttribute("href") || "";
                    var m = href.match(/[?&]tile=([a-z_0-9]+)/);
                    if (m) tile = m[1];
                }
                if (!tile) return;

                var keyword = tileToLabelKeyword[tile];
                if (keyword) {
                    var pillBtns = document.querySelectorAll('.st-key-promo_variant_pills button');
                    for (var k = 0; k < pillBtns.length; k++) {
                        var bText = (pillBtns[k].innerText || "").toLowerCase();
                        if (bText.indexOf(keyword) !== -1) {
                            e.preventDefault();
                            e.stopImmediatePropagation();
                            pillBtns[k].click();
                            return;
                        }
                    }
                }
            }, true);
        }

        // Global capture listener for audio player buttons & track seeking
        if (!window.__player_bound) {
            window.__player_bound = true;
            document.addEventListener("click", function(e) {
                var btn = e.target.closest(".player-play-btn");
                if (btn && !btn.disabled) {
                    e.preventDefault();
                    e.stopImmediatePropagation();

                    if (btn.__lastPlayClick && (Date.now() - btn.__lastPlayClick < 250)) return;
                    btn.__lastPlayClick = Date.now();

                    var audioId = btn.getAttribute("data-audio-id");
                    if (audioId) {
                        var fillId = btn.getAttribute("data-fill-id");
                        var timeId = btn.getAttribute("data-time-id");
                        if (fillId && timeId) {
                            window.bsInitCardTrack(audioId, fillId, timeId);
                        }
                        window.bsToggleAudio(audioId, btn);
                    }
                    return;
                }

                // Global capture listener for clicking anywhere on the track bar to seek
                var track = e.target.closest(".player-track");
                if (track) {
                    var pill = track.closest(".player-pill");
                    if (pill) {
                        var audio = pill.querySelector("audio");
                        if (audio && audio.duration) {
                            e.preventDefault();
                            e.stopImmediatePropagation();
                            var rect = track.getBoundingClientRect();
                            var clickX = e.clientX - rect.left;
                            var pct = Math.max(0, Math.min(1, clickX / rect.width));
                            audio.currentTime = pct * audio.duration;
                            var fill = pill.querySelector(".player-track-fill");
                            if (fill) fill.style.width = (pct * 100) + '%';
                            var pBtn = pill.querySelector(".player-play-btn");
                            if (pBtn && audio.paused) {
                                var pAudioId = pBtn.getAttribute("data-audio-id");
                                var pFillId = pBtn.getAttribute("data-fill-id");
                                var pTimeId = pBtn.getAttribute("data-time-id");
                                if (pFillId && pTimeId) {
                                    window.bsInitCardTrack(pAudioId, pFillId, pTimeId);
                                }
                                window.bsToggleAudio(pAudioId, pBtn);
                            }
                            return;
                        }
                    }
                }

                // Prevent card toggle when clicking ID link
                var idLink = e.target.closest(".card-meta-muted-link");
                if (idLink) {
                    e.stopPropagation();
                }
            }, true);
        }
    `;
    w.document.head.appendChild(s);
})();
</script>
""", height=0, width=0)

# 3. Hardware Detection & Engines
@st.cache_resource
def get_hardware_info() -> Tuple[Optional[str], int]:
    gpu_name = None
    vram_gb = 12
    try:
        import subprocess
        res = subprocess.run(
            ["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=1.5
        )
        if res.returncode == 0 and res.stdout.strip():
            parts = [p.strip() for p in res.stdout.strip().split(",")]
            gpu_name = parts[0]
            vram_mb = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 0
            if vram_mb > 0:
                vram_gb = round(vram_mb / 1024)
    except Exception:
        pass
    return gpu_name, vram_gb

detected_gpu, detected_vram = get_hardware_info()

@st.cache_resource(show_spinner=False)
def get_shared_transcriber():
    from transcriber import SpeechTranscriber
    w_cfg = load_config().get("whisper", {})
    return SpeechTranscriber(
        model_name=w_cfg.get("model_name", "large-v3"),
        device=w_cfg.get("device", "cuda"),
        compute_type=w_cfg.get("compute_type", "float16"),
        initial_prompt=w_cfg.get("initial_prompt"),
        vad_filter=w_cfg.get("vad_filter", True),
        vad_parameters=w_cfg.get("vad_parameters")
    )

def get_engine():
    eng = ScannerEngine()
    eng._transcriber = get_shared_transcriber()
    return eng

engine = get_engine()
db = engine.db
exporter = engine.exporter

# Handle query-param actions (e.g. Demucs vocal isolation trigger from card link)
if "demucs" in st.query_params:
    dem_vid = str(st.query_params["demucs"]).strip()
    try:
        del st.query_params["demucs"]
    except Exception:
        pass
    with st.spinner(f"Изоляция вокала через Demucs для видео {dem_vid}..."):
        try:
            engine.reprocess_video_with_demucs(dem_vid)
            st.success(f"Вокал для видео {dem_vid} успешно изолирован!")
        except Exception as ex:
            st.error(f"Ошибка Demucs: {ex}")
    st.rerun()

# Register and retrieve lightweight local media URL from Streamlit's media file manager
def get_audio_url(video_id: str) -> Optional[str]:
    # Prefer separated vocal track if available
    v_path = Path("data/temp_audio") / f"{video_id}_vocals.wav"
    p = v_path if (v_path.exists() and v_path.stat().st_size > 0) else (Path("data/temp_audio") / f"{video_id}.wav")
    if p.exists() and p.stat().st_size > 0:
        try:
            from streamlit import runtime
            if runtime.exists():
                url = runtime.get_instance().media_file_mgr.add(
                    str(p.resolve()), "audio/wav", f"coord_aud_{video_id}"
                )
                if not url.startswith("/") and not url.startswith("http"):
                    url = "/" + url
                return url
        except Exception:
            pass
    return None

def format_space_num(num: Union[int, float]) -> str:
    """Formats 20930 -> '20 930' with space delimiter."""
    try:
        return f"{int(num):,}".replace(",", " ")
    except Exception:
        return str(num)

def clean_html(s: str) -> str:
    """Removes all leading and trailing indentation from each line to prevent Markdown code block triggers."""
    return "\n".join(line.strip() for line in s.strip().splitlines() if line.strip())

def extract_highlighted_snippet(full_text: str, matched_phrase: str, words_around: int = 4) -> Tuple[str, str]:
    """Extracts a highlighted snippet around the matched promo phrase, returning (html_snippet, full_clean_text).
    All data is strictly html.escape'd to prevent XSS.
    """
    if not full_text:
        return "-", "-"
    clean_full = full_text.replace("\n", " ").strip()
    escaped_full = html.escape(clean_full)
    
    if not matched_phrase or matched_phrase in ("Ничего не найдено", "none"):
        disp = clean_full[:95] + ("..." if len(clean_full) > 95 else "")
        return html.escape(disp), escaped_full

    m = re.search(re.escape(matched_phrase), clean_full, re.IGNORECASE)
    if not m:
        words = [re.escape(w.replace("ё", "е")) for w in re.split(r"\s+", matched_phrase) if w]
        if words:
            pat_parts = ["".join([f"[{c}ё]" if c == "е" else c for c in w]) for w in words]
            pat = r"\b" + r"\s+".join(pat_parts)
            try:
                m = re.search(pat, clean_full, re.IGNORECASE)
            except Exception:
                m = None

    if not m:
        m = re.search(r"(?:улучш\w+.*?)(?:яйц\w+|скин\w+|рарк\w+).*?(?:кейсер\w*|апгрейд\w*|dotagrade\w*|грейд\w*)", clean_full, re.IGNORECASE)

    if m:
        start_idx, end_idx = m.start(), m.end()
        pre_text = clean_full[:start_idx]
        pre_words = pre_text.split()
        if len(pre_words) > words_around:
            pre_snippet = "... " + " ".join(pre_words[-words_around:]) + " "
        else:
            pre_snippet = " ".join(pre_words) + (" " if pre_words else "")
            
        match_snippet = clean_full[start_idx:end_idx]
        
        post_text = clean_full[end_idx:]
        post_words = post_text.split()
        if len(post_words) > words_around:
            post_snippet = " " + " ".join(post_words[:words_around]) + " ..."
        else:
            post_snippet = (" " if post_words else "") + " ".join(post_words)
            
        snippet_html = f"{html.escape(pre_snippet)}<mark class='hl-phrase'>{html.escape(match_snippet)}</mark>{html.escape(post_snippet)}"
        return snippet_html, escaped_full
    else:
        disp = clean_full[:95] + ("..." if len(clean_full) > 95 else "")
        return html.escape(disp), escaped_full

def get_display_confidence(r: Dict[str, Any]) -> str:
    """Calculates real fuzzy match score (0-100%) with 1 decimal place."""
    v = r.get("variant")
    if not v or v in ("none", "None"):
        return "–"
    can = TARGET_VARIANTS.get(v)
    if not can:
        return "–"
    norm_can = PhraseMatcher.normalize_text(can.original_phrase)
    snip = r.get("matched_phrase") or ""
    if snip and snip != "Ничего не найдено":
        norm_snip = PhraseMatcher.normalize_text(snip)
        r1 = fuzz.ratio(norm_can, norm_snip)
        r2 = fuzz.token_sort_ratio(norm_can, norm_snip)
        score = 0.65 * r1 + 0.35 * r2
        return f"{score:.1f}%"
    raw_conf = r.get("confidence")
    if raw_conf and float(raw_conf) > 0:
        return f"{float(raw_conf) * 100:.1f}%"
    return "–"

def get_db_counts(db_instance) -> Tuple[int, int]:
    """Returns (videos_count, transcriptions_count) safely from SQLite database."""
    try:
        with db_instance.get_connection() as conn:
            cur = conn.cursor()
            cur.execute("SELECT COUNT(*) FROM videos")
            v_c = cur.fetchone()[0]
            cur.execute("SELECT COUNT(*) FROM transcriptions")
            t_c = cur.fetchone()[0]
            return v_c, t_c
    except Exception:
        return 0, 0

@st.dialog("Удалить всю базу")
def confirm_wipe_database_dialog(v_count: int, t_count: int):
    st.markdown(
        f"""
        <div style="display:flex;align-items:center;gap:8px;font-size:16px;font-weight:600;color:#D03B3B;margin-bottom:8px;">
            <span style="font-size:20px;">⚠️</span> Удалить всю базу
        </div>
        <p style="margin:0 0 14px 0;font-size:13px;color:#9A9C98;line-height:1.5;">
            Будет удалено: <b style="color:#ECEBE6;">{v_count} видео</b>, <b style="color:#ECEBE6;">{t_count} транскрипций</b>.<br>
            Это действие <b style="color:#D03B3B;">нельзя отменить</b>.
        </p>
        <div style="font-size:12px;color:#9A9C98;margin-bottom:6px;">
            Введите слово <b style="color:#ECEBE6;">УДАЛИТЬ</b> для подтверждения:
        </div>
        """,
        unsafe_allow_html=True
    )
    confirm_text = st.text_input("Подтверждение", key="dlg_confirm_wipe_input", placeholder="УДАЛИТЬ", label_visibility="collapsed")
    
    col_c1, col_c2 = st.columns([1, 1])
    with col_c1:
        if st.button("Отмена", key="dlg_btn_cancel_wipe", use_container_width=True):
            st.rerun()
    with col_c2:
        is_matched = confirm_text.strip().upper() == "УДАЛИТЬ"
        if st.button("Удалить", key="dlg_btn_do_wipe", disabled=not is_matched, use_container_width=True):
            db.clear_database(only_test_data=False)
            st.toast(f"Удалено: {v_count} записей")
            st.rerun()

# 4. SECTION 1: HEADER
@st.cache_data(ttl=180, show_spinner=False)
def get_cached_update_info() -> Dict[str, Any]:
    try:
        return updater.check_for_updates()
    except Exception as e:
        return {"has_update": False, "local_sha": updater.get_local_version(), "remote_sha": "", "message": "", "error": str(e)}

@st.dialog("Обновление AdWhisper")
def show_update_dialog():
    with st.spinner("Проверка обновлений на GitHub..."):
        upd_res = updater.check_for_updates()
    has_update = upd_res.get("has_update", False)
    local_sha = upd_res.get("local_sha") or updater.get_local_version()
    remote_sha = upd_res.get("remote_sha") or local_sha
    msg = upd_res.get("message") or "Улучшения и исправления"
    date_str = upd_res.get("date") or ""
    err_str = upd_res.get("error")

    if has_update:
        st.markdown(
            f"""
            <div style="font-size: 15px; font-weight: 600; color: #C8F169; margin-bottom: 12px; display: flex; align-items: center; gap: 8px;">
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#C8F169" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg>
                Доступна новая версия AdWhisper!
            </div>
            <div style="background: #121314; border: 1px solid #2A2D30; border-radius: 8px; padding: 12px 14px; margin-bottom: 14px; font-size: 13px;">
                <div style="display: flex; justify-content: space-between; margin-bottom: 6px;">
                    <span style="color: #7A7C80;">Установленная версия:</span>
                    <span style="font-family: 'JetBrains Mono', monospace; color: #9A9C98;">{local_sha}</span>
                </div>
                <div style="display: flex; justify-content: space-between; margin-bottom: 6px;">
                    <span style="color: #7A7C80;">Свежая версия на GitHub:</span>
                    <span style="font-family: 'JetBrains Mono', monospace; color: #C8F169; font-weight: 600;">{remote_sha} ({date_str})</span>
                </div>
                <div style="margin-top: 8px; padding-top: 8px; border-top: 1px solid #222528; color: #ECEBE6; font-size: 12px; line-height: 1.4;">
                    <span style="color: #7A7C80;">Что нового:</span> <b>{html.escape(msg)}</b>
                </div>
            </div>
            <div style="font-size: 12px; color: #9A9C98; margin-bottom: 18px; line-height: 1.4;">
                Обновление загрузит только свежие скрипты программы (~300 КБ). Ваша база данных, кэш и настройки останутся в сохранности.
            </div>
            """,
            unsafe_allow_html=True
        )
        col_c1, col_c2 = st.columns([1, 1.2])
        with col_c1:
            if st.button("Отмена", key="btn_cancel_upd", use_container_width=True):
                if "update" in st.query_params:
                    del st.query_params["update"]
                st.rerun()
        with col_c2:
            if st.button("🚀 Обновить сейчас", key="btn_do_apply_upd", type="primary", use_container_width=True):
                import time
                with st.spinner("Загрузка обновления из GitHub..."):
                    ok, res_msg = updater.apply_update(remote_sha)
                if ok:
                    st.toast(res_msg)
                    get_cached_update_info.clear()
                    if "update" in st.query_params:
                        del st.query_params["update"]
                    try:
                        time.sleep(1)
                    except Exception:
                        pass
                    st.rerun()
                else:
                    st.error(res_msg)
    else:
        status_txt = f"Ошибка связи: {err_str}" if err_str else "У вас установлена последняя версия"
        status_color = "#D03B3B" if err_str else "#C8F169"
        st.markdown(
            f"""
            <div style="font-size: 15px; font-weight: 600; color: #ECEBE6; margin-bottom: 12px; display: flex; align-items: center; gap: 8px;">
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="{status_color}" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"/></svg>
                {status_txt}
            </div>
            <div style="background: #121314; border: 1px solid #2A2D30; border-radius: 8px; padding: 12px 14px; margin-bottom: 16px; font-size: 13px;">
                <div style="display: flex; justify-content: space-between; margin-bottom: 4px;">
                    <span style="color: #7A7C80;">Текущий коммит:</span>
                    <span style="font-family: 'JetBrains Mono', monospace; color: #C8F169;">{local_sha}</span>
                </div>
                <div style="font-size: 12px; color: #9A9C98; margin-top: 6px;">
                    {html.escape(msg) if msg else 'Все компоненты актуальны.'}
                </div>
            </div>
            """,
            unsafe_allow_html=True
        )
        col_u1, col_u2 = st.columns([1, 1])
        with col_u1:
            if st.button("Закрыть", key="btn_close_upd", use_container_width=True):
                if "update" in st.query_params:
                    del st.query_params["update"]
                st.rerun()
        with col_u2:
            if st.button("Проверить снова", key="btn_recheck_upd", use_container_width=True):
                get_cached_update_info.clear()
                st.rerun()

if "update" in st.query_params:
    show_update_dialog()

active_whisper_model = load_config().get("whisper", {}).get("model_name", "large-v3")
if icon_b64:
    header_icon_html = f'<img src="data:image/png;base64,{icon_b64}" width="36" height="36" style="border-radius: 9px; margin-right: 12px; object-fit: cover; box-shadow: 0 2px 8px rgba(0,0,0,0.4);">'
else:
    header_icon_html = """<svg width="32" height="32" viewBox="0 0 24 24" fill="#FFFFFF"><path d="M19.59 6.69a4.83 4.83 0 0 1-3.77-4.25V2h-3.45v13.67a2.89 2.89 0 0 1-5.2 1.74 2.89 2.89 0 0 1 2.31-4.64c.298-.002.595.042.88.13V9.4a6.33 6.33 0 0 0-1-.08A6.34 6.34 0 0 0 3 15.66a6.34 6.34 0 0 0 10.82 4.47 6.27 6.27 0 0 0 1.95-4.47V8.75a8.16 8.16 0 0 0 4.82 1.56V6.86a4.85 4.85 0 0 1-1-.17Z"/></svg>"""

update_info = get_cached_update_info()
has_upd = update_info.get("has_update", False)
upd_cls = "header-update-btn has-update" if has_upd else "header-update-btn"
upd_label = "⚡ Update" if has_upd else "Update"
upd_tooltip = f"Доступно обновление ({update_info.get('remote_sha')})! Нажмите для просмотра" if has_upd else "Проверить обновления приложения"

cur_qp = dict(st.query_params)
cur_qp["update"] = "1"
upd_href = f"?{urllib.parse.urlencode(cur_qp)}"

st.markdown(clean_html(f"""
<div class="banner-header">
    <div class="header-left">
        {header_icon_html}
        <div class="header-titles">
            <div class="header-app-name">AdWhisper</div>
            <div class="header-author">by @saha12cheh</div>
        </div>
    </div>
    <div class="header-pills">
        <a href="{upd_href}" target="_self" class="header-pill {upd_cls}" title="{upd_tooltip}">{upd_label}</a>
        <span class="header-pill">Whisper {active_whisper_model}</span>
        <span class="header-pill">Demucs</span>
        <span class="header-pill">yt-dlp</span>
    </div>
</div>
"""), unsafe_allow_html=True)

# 5. SECTION 2: PARAMETERS PANEL
today = date.today()
if "is_all_time" not in st.session_state:
    st.session_state.is_all_time = False

if "start_date_picker" not in st.session_state:
    st.session_state.start_date_picker = today - timedelta(days=6)
if "end_date_picker" not in st.session_state:
    st.session_state.end_date_picker = today

# Restore or initialize main_account_input
if "main_account_input" not in st.session_state:
    if "account" in st.query_params and str(st.query_params["account"]).strip():
        raw_acc = str(st.query_params["account"]).strip()
        st.session_state.main_account_input = f"https://www.tiktok.com/@{raw_acc.lstrip('@')}" if not raw_acc.startswith("http") else raw_acc
    elif not st.session_state.get("account_reset", False):
        latest_scans = db.get_latest_scans(1)
        if latest_scans and latest_scans[0].get("account") and latest_scans[0]["account"] not in ("unknown", "custom_urls", "local"):
            raw_acc = str(latest_scans[0]["account"]).strip()
            st.session_state.main_account_input = f"https://www.tiktok.com/@{raw_acc.lstrip('@')}" if not raw_acc.startswith("http") else raw_acc
            st.query_params["account"] = raw_acc.lstrip("@")
        else:
            st.session_state.main_account_input = ""
    else:
        st.session_state.main_account_input = ""

with st.container(border=True):
    # ROW 1: Profile URL + 5 Chip Buttons
    col_acc, col_c1, col_c2, col_c3, col_c4, col_c5 = st.columns([2.5, 0.7, 0.7, 0.7, 0.8, 0.7], vertical_alignment="bottom")
    with col_acc:
        account_input = st.text_input(
            "Профиль или ссылка TikTok",
            placeholder="https://www.tiktok.com/@username",
            key="main_account_input",
            label_visibility="visible"
        )
        if account_input and account_input.strip():
            st.session_state.account_reset = False
            u = TikTokCollector.extract_username(account_input)
            if u and st.query_params.get("account") != u:
                st.query_params["account"] = u
        elif not account_input or not account_input.strip():
            if "account" in st.query_params:
                del st.query_params["account"]
    with col_c1:
        if st.button("7 дней", key="chip_7d", use_container_width=True):
            st.session_state.is_all_time = False
            st.session_state.start_date_picker = today - timedelta(days=6)
            st.session_state.end_date_picker = today
            st.rerun()
    with col_c2:
        if st.button("14 дней", key="chip_14d", use_container_width=True):
            st.session_state.is_all_time = False
            st.session_state.start_date_picker = today - timedelta(days=13)
            st.session_state.end_date_picker = today
            st.rerun()
    with col_c3:
        if st.button("30 дней", key="chip_30d", use_container_width=True):
            st.session_state.is_all_time = False
            st.session_state.start_date_picker = today - timedelta(days=29)
            st.session_state.end_date_picker = today
            st.rerun()
    with col_c4:
        if st.button("Всё время", key="chip_all", use_container_width=True):
            st.session_state.is_all_time = True
            st.rerun()
    def on_chip_reset_click():
        st.session_state.is_all_time = False
        st.session_state.start_date_picker = today - timedelta(days=6)
        st.session_state.end_date_picker = today
        st.session_state.main_account_input = ""
        st.session_state.account_reset = True
        if "account" in st.query_params:
            del st.query_params["account"]

    with col_c5:
        st.button("Сброс", key="chip_reset", on_click=on_chip_reset_click, use_container_width=True)

    # ROW 2: Dates, Min Views, VRAM, Threads Slider, Run Scan Button
    col_d1, col_d2, col_mv, col_vr, col_th, col_btn = st.columns([1.1, 1.1, 0.9, 0.9, 1.4, 1.5], vertical_alignment="bottom")
    with col_d1:
        if st.session_state.is_all_time:
            st.text_input("Дата начала", value="За всё время", disabled=True)
            start_date_val = None
        else:
            start_date_val = st.date_input("Дата начала", key="start_date_picker", format="YYYY-MM-DD")
    with col_d2:
        if st.session_state.is_all_time:
            st.text_input("Дата конца", value="За всё время", disabled=True)
            end_date_val = None
        else:
            end_date_val = st.date_input("Дата конца", key="end_date_picker", format="YYYY-MM-DD")
    with col_mv:
        min_views_val = st.number_input("Мин. просмотров", min_value=0, value=2000, step=500)
    with col_vr:
        vram_val = st.number_input("VRAM GPU, ГБ", min_value=0, max_value=48, value=detected_vram if detected_vram else 12, step=2)

    # Thread recommendation based on VRAM
    calc_threads = 3 if vram_val >= 12 else (2 if vram_val >= 8 else 1)

    if "prev_vram" not in st.session_state:
        st.session_state.prev_vram = vram_val
        st.session_state.threads_slider = calc_threads
    elif st.session_state.prev_vram != vram_val:
        st.session_state.prev_vram = vram_val
        st.session_state.threads_slider = calc_threads

    curr_threads = st.session_state.get("threads_slider", calc_threads)

    with col_th:
        st.markdown(
            f'<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:6px;">'
            f'<span style="font-size:14px;color:#ECEBE6;">Потоков обработки</span>'
            f'<span style="font-size:14px;font-weight:600;color:#C8F169;font-family:\'JetBrains Mono\',monospace;">{curr_threads}</span>'
            f'</div>',
            unsafe_allow_html=True
        )
        num_threads_val = st.slider(
            "Потоков обработки",
            min_value=1,
            max_value=5,
            key="threads_slider",
            label_visibility="collapsed"
        )

    with col_btn:
        can_run = bool(account_input and account_input.strip())
        if not st.session_state.is_all_time:
            if start_date_val and end_date_val and start_date_val > end_date_val:
                can_run = False
        run_scan_btn = st.button("Запустить сканирование", key="main_run_scan", type="primary", disabled=not can_run, use_container_width=True)

    # Collapsible Advanced Settings (Expander with live status)
    cfg_whisper = load_config().get("whisper", {})
    curr_model_key = cfg_whisper.get("model_name", "large-v3")

    audio_dir = Path("data/temp_audio")
    audio_files_for_title = [f for f in audio_dir.glob("*.wav") if f.name != ".gitkeep"] if audio_dir.exists() else []
    audio_mb_for_title = round(sum(f.stat().st_size for f in audio_files_for_title) / (1024 * 1024), 1)

    expander_title = f"Дополнительные источники и база · Whisper {curr_model_key} · Кэш {audio_mb_for_title} МБ"
    adv_expanded = "open_adv" in st.query_params

    # Default containers for results outside expander
    manual_urls_raw = ""
    uploaded_audio_files = []

    with st.expander(expander_title, expanded=adv_expanded):
        st.markdown('<div class="extra-sources-container">', unsafe_allow_html=True)
        c_adv_model, c_adv_urls, c_adv_audio, c_adv_cache = st.columns(4, gap="medium")

        # ------------------- CARD 1: МОДЕЛЬ WHISPER -------------------
        with c_adv_model:
            st.markdown('<div class="bs-t">Модель Whisper</div>', unsafe_allow_html=True)
            models_specs = {
                "large-v3": {"size": "3.1 ГБ", "vram": 6.0},
                "large-v2": {"size": "3.1 ГБ", "vram": 6.0},
                "medium":   {"size": "1.5 ГБ", "vram": 3.0},
                "small":    {"size": "480 МБ", "vram": 1.5},
                "base":     {"size": "145 МБ", "vram": 1.0},
                "tiny":     {"size": "75 МБ",  "vram": 0.8},
            }
            m_keys = list(models_specs.keys())
            if curr_model_key not in models_specs:
                curr_model_key = "large-v3"
            sel_idx = m_keys.index(curr_model_key)

            chosen_model = st.selectbox(
                "Модель Whisper",
                options=m_keys,
                index=sel_idx,
                label_visibility="collapsed"
            )

            chosen_spec = models_specs[chosen_model]
            st.markdown(
                f'<div class="bs-row"><span>Размер: <b>{chosen_spec["size"]}</b></span><span>VRAM: <b>{chosen_spec["vram"]:.1f} ГБ</b></span></div>',
                unsafe_allow_html=True
            )

            # VRAM warning if required > user setting
            if vram_val < chosen_spec["vram"]:
                st.markdown(
                    f'<div style="color: #FFB347; font-size: 11px; margin-top: 2px;">⚠️ Требуется {chosen_spec["vram"]:.1f} ГБ VRAM (указано {vram_val} ГБ)</div>',
                    unsafe_allow_html=True
                )

            # Check if chosen_model is downloaded in local cache
            def is_whisper_downloaded(m_name: str) -> bool:
                try:
                    import faster_whisper
                    faster_whisper.download_model(m_name, local_files_only=True)
                    return True
                except Exception:
                    return False

            model_is_ready = is_whisper_downloaded(chosen_model)
            if model_is_ready:
                st.markdown('<div class="bs-badge"><span class="bs-dot"></span>Скачана в локальный кэш</div>', unsafe_allow_html=True)
            else:
                st.markdown('<div class="bs-badge" style="color: #FFB347;"><span class="bs-dot" style="background: #FFB347;"></span>Требуется загрузка</div>', unsafe_allow_html=True)

            btn_dl_label = "⟳ Скачать повторно" if model_is_ready else "⬇ Скачать модель"
            if st.button(btn_dl_label, key="btn_download_model_whisper", use_container_width=True):
                with st.spinner(f"Загрузка весов {chosen_model}..."):
                    try:
                        import faster_whisper
                        faster_whisper.download_model(chosen_model, local_files_only=False)
                        st.success(f"Модель {chosen_model} успешно загружена!")
                        cfg_path = Path("config.yaml")
                        if cfg_path.exists():
                            with open(cfg_path, "r", encoding="utf-8") as f:
                                ct = f.read()
                            ct = re.sub(r'model_name:\s*["\']?[a-zA-Z0-9_\-\.]+["\']?', f'model_name: "{chosen_model}"', ct)
                            with open(cfg_path, "w", encoding="utf-8") as f:
                                f.write(ct)
                        st.cache_resource.clear()
                        st.rerun()
                    except Exception as ex_dl:
                        st.error(f"Ошибка загрузки: {ex_dl}")

            if chosen_model != curr_model_key:
                if st.button("Применить выбор", key="btn_apply_model_whisper", type="primary", use_container_width=True):
                    cfg_path = Path("config.yaml")
                    if cfg_path.exists():
                        with open(cfg_path, "r", encoding="utf-8") as f:
                            ct = f.read()
                        ct = re.sub(r'model_name:\s*["\']?[a-zA-Z0-9_\-\.]+["\']?', f'model_name: "{chosen_model}"', ct)
                        with open(cfg_path, "w", encoding="utf-8") as f:
                            f.write(ct)
                    st.cache_resource.clear()
                    st.rerun()

        # ------------------- CARD 2: РУЧНОЙ ВВОД И COOKIES -------------------
        with c_adv_urls:
            st.markdown('<div class="bs-t">Ручной ввод и cookies</div>', unsafe_allow_html=True)
            manual_urls_raw = st.text_area(
                "Список ссылок:",
                height=72,
                placeholder="https://www.tiktok.com/@username/video/...",
                label_visibility="collapsed"
            )

            # Parse lines for counters and duplicate removal
            raw_lines = [line.strip() for line in manual_urls_raw.splitlines() if line.strip()]
            valid_urls = []
            invalid_urls = []
            seen_urls = set()
            dup_count = 0
            for u in raw_lines:
                if u in seen_urls:
                    dup_count += 1
                    continue
                seen_urls.add(u)
                if u.startswith("http://") or u.startswith("https://"):
                    valid_urls.append(u)
                else:
                    invalid_urls.append(u)

            inv_style = 'color: #D03B3B; font-weight:600;' if invalid_urls else 'color: #ECEBE6;'
            st.markdown(
                f"""
                <div class="bs-row">
                    <span>Ссылок: <b>{len(valid_urls)}</b> · <span style="{inv_style}">некорректных: <b>{len(invalid_urls)}</b></span></span>
                    <span>Дублей удалено: <b>{dup_count}</b></span>
                </div>
                """,
                unsafe_allow_html=True
            )

            # Cookies section
            cookies_path = Path("data/temp_cookies.txt")
            has_cookies = cookies_path.exists() and cookies_path.stat().st_size > 0

            if has_cookies:
                try:
                    with open(cookies_path, "r", encoding="utf-8", errors="ignore") as f:
                        c_lines = [l for l in f.read().splitlines() if l.strip() and not l.startswith("#")]
                    c_domains = {l.split()[0] for l in c_lines if len(l.split()) >= 7}
                    c_badge = f"{len(c_lines)} записей · {len(c_domains)} доменов"
                except Exception:
                    c_badge = "активны"

                st.markdown(
                    f"""
                    <div style="display:flex;align-items:center;justify-content:space-between;background:#121314;border:0.5px solid #2A2D30;border-radius:8px;padding:8px 10px;margin-top:6px;font-size:12px;">
                        <span>🍪 <b>cookies.txt</b> ({c_badge})</span>
                    </div>
                    """,
                    unsafe_allow_html=True
                )
                if st.button("✕ Удалить cookies", key="btn_remove_cookies", use_container_width=True):
                    try:
                        cookies_path.unlink(missing_ok=True)
                    except Exception:
                        pass
                    if hasattr(engine, 'collector'):
                        engine.collector.cookies_file = None
                    if hasattr(engine, 'downloader'):
                        engine.downloader.cookies_file = None
                    st.rerun()
            else:
                uploaded_cookies_file = st.file_uploader(
                    "Файл cookies (Netscape cookies.txt):",
                    type=["txt"],
                    key="uploader_netscape_cookies",
                    label_visibility="collapsed"
                )
                if uploaded_cookies_file:
                    raw_bytes = uploaded_cookies_file.read()
                    text_content = raw_bytes.decode("utf-8", errors="ignore")
                    lines = [ln.strip() for ln in text_content.splitlines() if ln.strip()]
                    first_line = lines[0] if lines else ""
                    if "# Netscape HTTP Cookie File" not in first_line and "# HTTP Cookie File" not in first_line:
                        st.error("Ошибка: Файл не соответствует формату Netscape cookies.txt (нет заголовка '# Netscape HTTP Cookie File')")
                    else:
                        cookies_path.parent.mkdir(parents=True, exist_ok=True)
                        with open(cookies_path, "wb") as f:
                            f.write(raw_bytes)
                        try:
                            import os
                            os.chmod(cookies_path, 0o600)
                        except Exception:
                            pass
                        if hasattr(engine, 'collector'):
                            engine.collector.cookies_file = str(cookies_path)
                        if hasattr(engine, 'downloader'):
                            engine.downloader.cookies_file = str(cookies_path)
                        st.toast("Cookies успешно загружены и сохранены (права 600)")
                        st.rerun()

                st.markdown(
                    '<div class="bs-s" style="font-size:11px;margin-top:4px;">Cookies нужны для закрытых/возрастных видео · <a href="https://github.com/yt-dlp/yt-dlp/wiki/Extractors#exporting-youtube-cookies" target="_blank" style="color:#C8F169;text-decoration:none;">Инструкция ↗</a></div>',
                    unsafe_allow_html=True
                )

        # ------------------- CARD 3: ПРЯМАЯ ЗАГРУЗКА АУДИО -------------------
        with c_adv_audio:
            st.markdown('<div class="bs-t">Прямая загрузка аудио</div>', unsafe_allow_html=True)
            uploaded_audio_files = st.file_uploader(
                "Загрузить аудио:",
                type=["mp3", "wav", "m4a", "ogg"],
                accept_multiple_files=True,
                key="uploader_direct_audio",
                label_visibility="collapsed"
            )

            if uploaded_audio_files:
                for af in uploaded_audio_files:
                    sz_mb = round(af.size / (1024 * 1024), 1)
                    st.markdown(
                        f"""
                        <div style="display:flex;align-items:center;gap:8px;font-size:12px;border:0.5px solid #2A2D30;border-radius:8px;padding:6px 10px;background:#121314;margin-top:4px;">
                            <span>🎵</span>
                            <span style="flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;color:#ECEBE6;">{af.name}</span>
                            <span style="color:#9A9C98;">{sz_mb} МБ</span>
                            <span style="color:#C8F169;font-weight:500;">✓ Готов</span>
                        </div>
                        """,
                        unsafe_allow_html=True
                    )
            else:
                st.markdown(
                    '<div class="bs-s" style="text-align:center;font-size:11px;margin-top:8px;color:#5A5D62;">Поддерживаются MP3, WAV, M4A, OGG до 200 МБ</div>',
                    unsafe_allow_html=True
                )

        # ------------------- CARD 4: КЭШ И БАЗА ДАННЫХ -------------------
        with c_adv_cache:
            st.markdown('<div class="bs-t">Кэш и база данных</div>', unsafe_allow_html=True)

            # Audio cache stats
            audio_dir = Path("data/temp_audio")
            audio_files = [f for f in audio_dir.glob("*.wav") if f.name != ".gitkeep"] if audio_dir.exists() else []
            audio_bytes = sum(f.stat().st_size for f in audio_files)
            audio_mb = round(audio_bytes / (1024 * 1024), 1)

            st.markdown(
                f"""
                <div style="display:flex;flex-direction:column;gap:4px;">
                    <div class="bs-row">
                        <span>Кэш аудио</span>
                        <b>{len(audio_files)} файлов · {audio_mb} МБ</b>
                    </div>
                </div>
                """,
                unsafe_allow_html=True
            )

            btn_cache_empty = (len(audio_files) == 0)
            cache_hint = "Кэш пуст" if btn_cache_empty else "Очистить временные аудиофайлы (обратимо)"
            if st.button("🗑 Очистить кэш аудио", key="btn_clear_audio_cache", disabled=btn_cache_empty, help=cache_hint, use_container_width=True):
                count_cleaned = len(audio_files)
                for af in audio_files:
                    try:
                        af.unlink(missing_ok=True)
                    except Exception:
                        pass
                st.toast(f"Кэш аудио очищен (удалено {count_cleaned} файлов, {audio_mb} МБ)")
                st.rerun()

            # Database stats
            v_cnt, t_cnt = get_db_counts(db)
            db_file = Path("data/scanner.db")
            db_size_mb = round(db_file.stat().st_size / (1024 * 1024), 1) if db_file.exists() else 0.0

            st.markdown(
                f"""
                <div style="display:flex;flex-direction:column;gap:4px;margin-top:4px;">
                    <div class="bs-row">
                        <span>База данных</span>
                        <b>{v_cnt} видео · {db_size_mb} МБ</b>
                    </div>
                </div>
                """,
                unsafe_allow_html=True
            )

            # Dangerous Zone
            st.markdown(
                """
                <div style="border-top:0.5px solid #2A2D30; padding-top:10px; margin-top:auto;">
                    <div class="bs-t" style="color:#D03B3B;">Опасная зона</div>
                </div>
                """,
                unsafe_allow_html=True
            )

            if st.button("⚠ Очистить всю базу…", key="btn_open_wipe_db_dialog", use_container_width=True):
                confirm_wipe_database_dialog(v_cnt, t_cnt)

        st.markdown('</div>', unsafe_allow_html=True)

# 6. SCAN EXECUTION HANDLER
if run_scan_btn:
    # Adapt transcriber device and compute_type based on user's manual VRAM setting
    if hasattr(engine, 'transcriber') and engine.transcriber:
        if vram_val == 0:
            engine.transcriber.device = "cpu"
            engine.transcriber.compute_type = "int8"
        elif vram_val < 5:
            engine.transcriber.device = "cuda"
            engine.transcriber.compute_type = "int8"
        elif vram_val < 8:
            engine.transcriber.device = "cuda"
            engine.transcriber.compute_type = "int8_float16"
        else:
            engine.transcriber.device = "cuda"
            engine.transcriber.compute_type = "float16"
    progress_bar = st.progress(0.0)
    status_text = st.empty()

    def update_progress(msg: str, pct: float):
        try:
            progress_bar.progress(min(1.0, max(0.0, pct)))
            status_text.text(msg)
        except Exception:
            pass

    custom_urls_list = []
    if manual_urls_raw.strip():
        custom_urls_list = [u.strip() for u in manual_urls_raw.splitlines() if u.strip()]

    s_dt = datetime(start_date_val.year, start_date_val.month, start_date_val.day, 0, 0, 0) if (start_date_val and not st.session_state.is_all_time) else None
    e_dt = datetime(end_date_val.year, end_date_val.month, end_date_val.day, 23, 59, 59) if (end_date_val and not st.session_state.is_all_time) else None

    if uploaded_audio_files:
        for idx, af in enumerate(uploaded_audio_files):
            update_progress(f"Обработка {af.name} ({idx+1}/{len(uploaded_audio_files)})...", (idx+1)/len(uploaded_audio_files))
            saved_p = Path("data/temp_audio") / af.name
            saved_p.parent.mkdir(parents=True, exist_ok=True)
            with open(saved_p, "wb") as f:
                f.write(af.read())
            vid_id = Path(af.name).stem
            engine.process_local_audio_file(str(saved_p), video_id=vid_id)
        st.rerun()

    scan_outcome = engine.run_scan(
        channel_url=account_input,
        start_date=s_dt,
        end_date=e_dt,
        min_views=min_views_val,
        custom_urls=custom_urls_list if custom_urls_list else None,
        num_threads=num_threads_val,
        progress_callback=update_progress
    )
    st.rerun()

# 7. DATA RETRIEVAL FOR SELECTED DATE RANGE
active_start_date = start_date_val if (start_date_val and not st.session_state.is_all_time) else None
active_end_date = end_date_val if (end_date_val and not st.session_state.is_all_time) else None

# Determine target account from input
curr_target_user = TikTokCollector.extract_username(account_input) if account_input else ""

# All videos collected in range (isolated per account to prevent data cross-contamination)
if curr_target_user:
    all_collected = db.get_results_table_data("all_collected", start_date=active_start_date, end_date=active_end_date, author=curr_target_user)
elif manual_urls_raw.strip() or uploaded_audio_files:
    all_collected = db.get_results_table_data("all_collected", start_date=active_start_date, end_date=active_end_date)
else:
    all_collected = []
total_collected_cnt = len(all_collected)

# Separate subsets
upgrade_rows = [r for r in all_collected if r.get("variant") == "variant_2" and r.get("video_status") == "analyzed"]
keyser_rows = [r for r in all_collected if r.get("variant") == "variant_1" and r.get("video_status") == "analyzed"]
dotagrade_rows = [r for r in all_collected if r.get("variant") == "variant_3" and r.get("video_status") == "analyzed"]
all_promo_rows = [r for r in all_collected if r.get("variant") in ("variant_1", "variant_2", "variant_3") and r.get("video_status") == "analyzed"]
no_promo_rows = [r for r in all_collected if r.get("variant") in ("none", None) and r.get("video_status") == "analyzed"]

filtered_views_rows = [r for r in all_collected if r.get("video_status") == "filtered_views"]
filtered_date_rows = [r for r in all_collected if r.get("video_status") == "filtered_date"]
error_rows = [r for r in all_collected if r.get("video_status") in ("error", "poor_quality")]
doubtful_rows = [r for r in all_collected if r.get("is_doubtful") and r.get("video_status") == "analyzed"]

cnt_upgrade = len(upgrade_rows)
cnt_keyser = len(keyser_rows)
cnt_dotagrade = len(dotagrade_rows)
cnt_all_promo = len(all_promo_rows)
cnt_no_promo = len(no_promo_rows)
cnt_filtered_views = len(filtered_views_rows)
cnt_filtered_date = len(filtered_date_rows)
cnt_filtered_total = cnt_filtered_views + cnt_filtered_date
cnt_errors = len(error_rows)
cnt_doubtful = len(doubtful_rows)

views_upgrade = sum(int(r.get("views") or 0) for r in upgrade_rows)
views_keyser = sum(int(r.get("views") or 0) for r in keyser_rows)
views_dotagrade = sum(int(r.get("views") or 0) for r in dotagrade_rows)
views_all_promo = sum(int(r.get("views") or 0) for r in all_promo_rows)
views_no_promo = sum(int(r.get("views") or 0) for r in no_promo_rows)
views_filtered = sum(int(r.get("views") or 0) for r in filtered_views_rows)
views_all = sum(int(r.get("views") or 0) for r in all_collected)

# Calculate days inclusive: N
if active_start_date and active_end_date:
    calc_days = (active_end_date - active_start_date).days + 1
else:
    timestamps = [r.get("upload_timestamp") for r in all_collected if r.get("upload_timestamp")]
    if timestamps:
        min_d = datetime.fromtimestamp(min(timestamps)).date()
        max_d = datetime.fromtimestamp(max(timestamps)).date()
        calc_days = (max_d - min_d).days + 1
    else:
        calc_days = 1

# Total analyzed for promo percent
total_tested = cnt_all_promo + cnt_no_promo

# Strict balance formula: найдено = отсеяно + проверено + ошибки
unaccounted = total_collected_cnt - (cnt_filtered_total + total_tested + cnt_errors)
if unaccounted > 0:
    cnt_errors += unaccounted

# Percentage with proper rounding (e.g. 40/41 = 98%)
promo_pct = round((cnt_all_promo / max(1, total_tested)) * 100) if total_tested else 0

# 8. SECTION 3: FILTER TILES (Grid)
if "tile" in st.query_params:
    st.session_state.selected_tile = str(st.query_params["tile"]).strip()
    if st.session_state.selected_tile in ("keyser", "upgrade", "dotagrade", "all_promo"):
        st.session_state.promo_variant_pills = st.session_state.selected_tile
elif "selected_tile" not in st.session_state:
    st.session_state.selected_tile = "keyser"  # Matches mockup default
    st.session_state.promo_variant_pills = "keyser"

sel_tile = st.session_state.selected_tile

# Determine active stats for Tile 6 (Views tile)
cat_views_map = {
    "upgrade": ("Upgrader", views_upgrade, cnt_upgrade),
    "keyser": ("Caser", views_keyser, cnt_keyser),
    "dotagrade": ("DotaGrade", views_dotagrade, cnt_dotagrade),
    "all_promo": ("Всего с рекламой", views_all_promo, cnt_all_promo),
    "no_promo": ("Без рекламы", views_no_promo, cnt_no_promo),
    "views": ("Отсеяно по ТЗ", views_filtered, cnt_filtered_views),
    "all_collected": ("Все публикации", views_all, total_collected_cnt),
    "doubtful": ("Сомнительные", sum(int(r.get("views") or 0) for r in doubtful_rows), cnt_doubtful)
}

cur_cat_name, cur_cat_views, cur_cat_count = cat_views_map.get(sel_tile, ("Caser", views_keyser, cnt_keyser))

# Dynamic calculations for views tile sizing & font size (expanding when 6+ digits)
clean_views_int = int(cur_cat_views or 0)
num_digits = len(str(clean_views_int))
grid_expand_cls = "views-expanded" if num_digits >= 6 else ""

if num_digits >= 9:
    views_font_size = "18px"
elif num_digits >= 8:
    views_font_size = "20px"
elif num_digits >= 7:
    views_font_size = "22px"
elif num_digits >= 6:
    views_font_size = "24px"
else:
    views_font_size = "28px"

views_disp_html = format_space_num(cur_cat_views).replace(" ", "&nbsp;")

if cnt_errors > 0:
    bottom_stat_text = f"Отсеяно: {format_space_num(cnt_filtered_views)} · Проверено: {format_space_num(total_tested)} · Ошибок: {format_space_num(cnt_errors)}"
else:
    bottom_stat_text = f"Отсеяно до {format_space_num(min_views_val)}: {format_space_num(cnt_filtered_views)} из {format_space_num(total_collected_cnt)}"

# Render Tiles Grid (Pure CSS Grid, exactly 1 row of 6 tiles, no empty columns)
acc_qs = f"&account={urllib.parse.quote(curr_target_user)}" if curr_target_user else ""
tiles_grid_html = (
    f'<div class="filter-tiles-grid {grid_expand_cls}">'
    f'<a href="?tile=keyser{acc_qs}" data-tile="keyser" target="_self" class="tile-card {"active" if sel_tile == "keyser" else ""}"><div class="tile-label">Caser</div><div class="tile-num">{cnt_keyser}</div></a>'
    f'<a href="?tile=upgrade{acc_qs}" data-tile="upgrade" target="_self" class="tile-card {"active" if sel_tile == "upgrade" else ""}"><div class="tile-label">Upgrader</div><div class="tile-num">{cnt_upgrade}</div></a>'
    f'<a href="?tile=dotagrade{acc_qs}" data-tile="dotagrade" target="_self" class="tile-card {"active" if sel_tile == "dotagrade" else ""}"><div class="tile-label">DotaGrade</div><div class="tile-num">{cnt_dotagrade}</div></a>'
    f'<a href="?tile=all_promo{acc_qs}" data-tile="all_promo" target="_self" class="tile-card {"active" if sel_tile == "all_promo" else ""}"><div class="tile-label">Всего с рекламой</div><div class="tile-num">{cnt_all_promo}</div><div class="tile-subtext">{promo_pct}% от {total_tested} проверенных</div></a>'
    f'<a href="?tile=no_promo{acc_qs}" data-tile="no_promo" target="_self" class="tile-card {"active" if sel_tile == "no_promo" else ""}"><div class="tile-label">Без рекламы</div><div class="tile-num">{cnt_no_promo}</div><div class="tile-subtext">Обычный контент</div></a>'
    f'<a href="?tile=views{acc_qs}" data-tile="views" target="_self" class="tile-card {"active" if sel_tile == "views" else ""}">'
    f'<div class="views-tile-body">'
    f'<div class="views-tile-top">'
    f'<div class="tile-label">Просмотры · {cur_cat_name}</div>'
    f'<div class="views-tile-num" style="font-size: {views_font_size};">{views_disp_html}</div>'
    f'<div class="views-tile-sub">за {calc_days} дней · {cur_cat_count} видео</div>'
    f'</div>'
    f'<div class="views-tile-divider"></div>'
    f'<div class="views-tile-bottom">{bottom_stat_text}</div>'
    f'</div>'
    f'</a>'
    f'</div>'
)
st.markdown(clean_html(tiles_grid_html), unsafe_allow_html=True)

# 9. SECTION 4: RESULTS OF THE SELECTED CATEGORY
# Configure category metadata & explicit variant mapping
cat_config = {
    "keyser": {
        "title": "Caser",
        "var_num": "1",
        "canonical_name": "Яйцо в баттлпассе Caser",
        "h1": "«А улучшить своё яйцо ты можешь в баттлпассе Caser»",
        "tooltip": "Рекламный баннер Caser (ключевые слова: улучшить, яйцо, баттлпасс, caser, кейсер). Эталонная фраза: «А улучшить своё яйцо ты можешь в баттлпассе Caser»",
        "rows": keyser_rows
    },
    "upgrade": {
        "title": "Upgrader",
        "var_num": "2",
        "canonical_name": "Скины на Upgrader",
        "h1": "«А улучшить свои скины ты можешь на Upgrader»",
        "tooltip": "Рекламный баннер сервиса Upgrader (ключевые слова: улучшить, скины, upgrader, апгрейд). Эталонная фраза: «А улучшить свои скины ты можешь на Upgrader»",
        "rows": upgrade_rows
    },
    "dotagrade": {
        "title": "DotaGrade",
        "var_num": "3",
        "canonical_name": "Рарки на подарки на DotaGrade",
        "h1": "«А улучшить рарки на подарки ты можешь на DotaGrade»",
        "tooltip": "Рекламный баннер DotaGrade (ключевые слова: улучшить, рарки на подарки, dotagrade). Эталонная фраза: «А улучшить рарки на подарки ты можешь на DotaGrade»",
        "rows": dotagrade_rows
    },
    "all_promo": {
        "title": "Всего с рекламой",
        "var_num": "",
        "canonical_name": "Все найденные рекламные интеграции",
        "h1": "«Все найденные рекламные интеграции»",
        "tooltip": "Все публикации аккаунта, в которых распознаны целевые рекламные баннеры (Варианты №1, №2, №3)",
        "rows": all_promo_rows
    },
    "no_promo": {
        "title": "Без рекламы",
        "var_num": "",
        "canonical_name": "Обычный контент",
        "h1": "«Публикации без целевых рекламных фраз»",
        "tooltip": "Видео, проверенные через AI Whisper, в которых не обнаружено целевых рекламных интеграций",
        "rows": no_promo_rows
    },
    "views": {
        "title": "Отсеяно по просмотрам",
        "var_num": "",
        "canonical_name": f"Просмотры ≤ {format_space_num(min_views_val)}",
        "h1": f"«Публикации с просмотрами ≤ {format_space_num(min_views_val)}»",
        "tooltip": f"Видео, отсеянные по порогу ТЗ (просмотры ≤ {format_space_num(min_views_val)}) до скачивания аудиодорожки",
        "rows": filtered_views_rows
    },
    "all_collected": {
        "title": "Все публикации",
        "var_num": "",
        "canonical_name": "Все собранные публикации",
        "h1": "«Все собранные публикации аккаунта»",
        "tooltip": "Все публикации профиля, полученные за указанный период сканирования",
        "rows": all_collected
    },
    "doubtful": {
        "title": "Сомнительные",
        "var_num": "",
        "canonical_name": "Сомнительные совпадения (45–74%)",
        "h1": "«Публикации с сомнительными совпадениями (45–74%)»",
        "tooltip": "Видео с частичным совпадением, требующие проверки или изоляции вокала через Demucs",
        "rows": doubtful_rows
    }
}

active_cfg = cat_config.get(sel_tile, cat_config["keyser"])
active_rows = active_cfg["rows"]
active_m = len(active_rows)

if active_cfg["var_num"]:
    meta_prefix = f"{active_cfg['title']} · Вариант №{active_cfg['var_num']} · {active_m} видео"
else:
    meta_prefix = f"{active_cfg['title']} · {active_m} видео"

# Prepare URLs for copy and download (with guaranteed fallback to constructed TikTok URL)
cur_urls = []
for r in active_rows:
    v_id = str(r.get("video_id") or r.get("id") or "").strip()
    auth_name = (r.get("author") or curr_target_user or "video").lstrip("@")
    u = (r.get("video_url") or r.get("url") or (f"https://www.tiktok.com/@{auth_name}/video/{v_id}" if v_id else "")).strip()
    if u:
        cur_urls.append(u)
urls_text = "\n".join(cur_urls)
urls_escaped_json = html.escape(json.dumps(cur_urls, ensure_ascii=False), quote=True)
urls_escaped_plain = html.escape(urls_text, quote=True)
txt_data_uri = "data:text/plain;charset=utf-8," + urllib.parse.quote(urls_text)

doubtful_pill_html = ""
if cnt_doubtful > 0:
    active_cls = "active" if sel_tile == "doubtful" else ""
    doubtful_pill_html = f'<span style="color: #2A2D30; margin: 0 4px;">|</span><a href="?tile=doubtful" target="_self" class="results-pill-filter {active_cls}">Сомнительные ({cnt_doubtful})</a>'

escaped_tooltip = html.escape(active_cfg['tooltip'], quote=True)

results_bar_html = f"""
<div class="results-header-bar">
    <div class="results-header-left">
        <div class="results-meta-line">
            <span>{meta_prefix}</span>
            <span class="meta-tooltip-pill" title="{escaped_tooltip}">ⓘ Логика группировки</span>
            {doubtful_pill_html}
        </div>
        <h1 class="results-title-h1">{active_cfg["h1"]}</h1>
    </div>
    <div class="results-header-actions">
        <div class="copy-btn-anchor-wrapper">
            <button type="button" id="copy_links_btn_main" class="action-btn-copy" data-links="{urls_escaped_json}" data-plain-text="{urls_escaped_plain}" data-count="{active_m}">Скопировать ссылки ({active_m})</button>
            <div id="adwhisper_copy_toast_anchor" class="copy-button-toast-anchor"></div>
        </div>
        <a href="{txt_data_uri}" download="adwhisper_{sel_tile}.txt" class="action-btn-outline">Скачать .txt</a>
    </div>
</div>
"""
st.markdown(clean_html(results_bar_html), unsafe_allow_html=True)

# Sub-variants pills for promo variants (Instant in-place switching without page reload / disconnect)
if sel_tile in ("keyser", "upgrade", "dotagrade", "all_promo"):
    sub_options = ["keyser", "upgrade", "dotagrade", "all_promo"]
    sub_labels = {
        "keyser": f"Вариант 1: Caser ({cnt_keyser})",
        "upgrade": f"Вариант 2: Upgrader ({cnt_upgrade})",
        "dotagrade": f"Вариант 3: DotaGrade ({cnt_dotagrade})",
        "all_promo": f"Все рекламные ({cnt_all_promo})"
    }
    def on_promo_pill_change():
        new_sub = st.session_state.get("promo_variant_pills")
        if new_sub:
            st.session_state.selected_tile = new_sub
            st.query_params["tile"] = new_sub
            if curr_target_user:
                st.query_params["account"] = curr_target_user

    chosen_sub = st.pills(
        "Выбор рекламного варианта",
        options=sub_options,
        format_func=lambda x: sub_labels[x],
        key="promo_variant_pills",
        on_change=on_promo_pill_change,
        label_visibility="collapsed"
    )



# 10. RESULTS TABLE
if not active_rows:
    if not curr_target_user:
        st.markdown(
            '<div class="table-card" style="padding: 36px; text-align: center; color: #9A9C98;">'
            '<div style="font-size: 26px; margin-bottom: 8px;">🎬</div>'
            '<div style="font-size: 15px; font-weight: 500; color: #ECEBE6; margin-bottom: 6px;">Готов к сканированию</div>'
            '<div style="font-size: 13px;">Вставьте ссылку на профиль TikTok (например, <code>https://www.tiktok.com/@username</code>) и нажмите <b>«Запустить сканирование»</b>.</div>'
            '</div>',
            unsafe_allow_html=True
        )
    else:
        extra_hint = ""
        cnt_filtered = len(filtered_views_rows)
        if cnt_filtered > 0:
            extra_hint = f"<div style='font-size: 13px; margin-top: 8px; color: #7A7C80;'>Собрано публикаций аккаунта: <b>{total_collected_cnt}</b> (из них <b>{cnt_filtered}</b> отсеяно по порогу просмотров ≤ {format_space_num(min_views_val)}). Вы можете просмотреть их, перейдя на плитку <b>«Отсеяно по просмотрам»</b> или <b>«Все публикации»</b> вверху.</div>"
        st.markdown(
            f'<div class="table-card" style="padding: 24px; color: #9A9C98;">'
            f'<div style="font-size: 15px; color: #ECEBE6;">В выбранной категории «{active_cfg["title"]}» нет публикаций для <b>@{html.escape(curr_target_user)}</b>.</div>'
            f'{extra_hint}'
            f'</div>',
            unsafe_allow_html=True
        )
else:
    table_rows_html = []

    for idx, r in enumerate(active_rows, start=1):
        v_id = str(r.get("video_id") or "")
        auth_name = (r.get("author") or curr_target_user or "video").lstrip("@")
        v_url = r.get("video_url") or f"https://www.tiktok.com/@{auth_name}/video/{v_id}"
        views_s = format_space_num(r.get("views", 0))
        u_date = str(r.get("upload_date") or "")[:16]
        tc = r.get("timecode") or "-"
        tc_disp = tc.replace(" - ", " – ") if tc != "-" else "-"
        
        conf_str = get_display_confidence(r)
        
        raw_text = r.get("transcription") or (r.get("error_message") or "-")
        snip_html, clean_full_escaped = extract_highlighted_snippet(raw_text, r.get("matched_phrase") or "")
        
        escaped_url = html.escape(v_url, quote=True)
        id_html = f'<a href="{escaped_url}" target="_blank" rel="noopener noreferrer" class="td-id-link">{html.escape(v_id)}</a>'

        trans_cell = f'<details class="tbl-trans-details"><summary class="tbl-trans-summary" title="Нажмите, чтобы развернуть полную транскрипцию">{snip_html}</summary><div class="tbl-trans-full">{clean_full_escaped}</div></details>'

        table_rows_html.append(
            f'<tr>'
            f'<td class="td-num">#{idx}</td>'
            f'<td class="td-id">{id_html}</td>'
            f'<td class="td-views">{views_s}</td>'
            f'<td class="td-muted">{u_date}</td>'
            f'<td class="td-timecode">{tc_disp}</td>'
            f'<td class="td-conf">{conf_str}</td>'
            f'<td class="td-transcript">{trans_cell}</td>'
            f'</tr>'
        )

    table_full_html = (
        '<div class="table-card">'
        '<table class="spec-table">'
        '<thead><tr>'
        '<th style="text-align: center; width: 48px;" class="th-num">#</th>'
        '<th style="width: 170px;">ID видео</th>'
        '<th style="text-align: right; width: 90px;" class="th-views">Просмотры</th>'
        '<th style="width: 135px;">Опубликовано (UTC)</th>'
        '<th style="text-align: center; width: 105px;" class="th-timecode">Таймкод</th>'
        '<th style="text-align: center; width: 110px;" class="th-conf" title="Степень совпадения с эталонной фразой (fuzzy-match, 0–100%)">Уверенность</th>'
        '<th>Транскрипция</th>'
        '</tr></thead>'
        '<tbody>'
        + ''.join(table_rows_html)
        + '</tbody></table></div>'
    )
    st.markdown(clean_html(table_full_html), unsafe_allow_html=True)

# 11. SECTION 5: PUBLICATION CARDS & AUDIO PLAYERS (BOTTOM DETAILS)
chevron_svg = '<svg class="chevron-icon" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><polyline points="9 6 15 12 9 18"></polyline></svg>'

cards_list_html = []
for idx, r in enumerate(active_rows, start=1):
    v_id = str(r.get("video_id") or "")
    views_s = format_space_num(r.get("views", 0))
    u_date = str(r.get("upload_date") or "")
    tc = r.get("timecode") or "-"
    tc_disp = tc.replace(" - ", " – ") if tc != "-" else "–"
    auth_name = (r.get("author") or curr_target_user or "video").lstrip("@")
    v_url = r.get("video_url") or f"https://www.tiktok.com/@{auth_name}/video/{v_id}"
    
    var_tag = r.get("variant")
    if var_tag == "variant_1":
        var_num_label = "Вариант 1"
        cat_pill_label = "Кейсер"
    elif var_tag == "variant_2":
        var_num_label = "Вариант 2"
        cat_pill_label = "Апгрейд"
    elif var_tag == "variant_3":
        var_num_label = "Вариант 3"
        cat_pill_label = "Dotagrade"
    else:
        var_num_label = "Публикация"
        cat_pill_label = "Без рекламы"

    conf_str = get_display_confidence(r)
    raw_transcript = r.get("transcription") or (r.get("error_message") or "Транскрипция не сформирована")
    _, clean_full_escaped = extract_highlighted_snippet(raw_transcript, r.get("matched_phrase") or "")
    escaped_v_url = html.escape(v_url, quote=True)

    duration_sec = int(r.get("duration") or 34)
    dur_m = duration_sec // 60
    dur_s = f"{duration_sec % 60:02d}"
    dur_str = f"{dur_m}:{dur_s}"

    audio_url = get_audio_url(v_id)
    player_id = f"card_aud_{v_id}"
    fill_id = f"cfill_{v_id}"
    time_id = f"ctime_{v_id}"

    open_attr = "open" if idx == 1 else ""

    if audio_url:
        player_html = (
            f'<div class="player-pill">'
            f'<audio id="{player_id}" src="{audio_url}" preload="none"></audio>'
            f'<button class="player-play-btn" data-audio-id="{player_id}" data-fill-id="{fill_id}" data-time-id="{time_id}" aria-label="Воспроизвести">'
            f'<svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor"><polygon points="6 4 20 12 6 20 6 4"></polygon></svg>'
            f'</button>'
            f'<div class="player-track">'
            f'<div id="{fill_id}" class="player-track-fill" style="width: 0%;"></div>'
            f'</div>'
            f'<div id="{time_id}" class="player-time">0:00 / {dur_str}</div>'
            f'</div>'
        )
    else:
        player_html = (
            f'<div class="player-pill" style="opacity: 0.4;">'
            f'<button class="player-play-btn" disabled style="cursor: not-allowed;">'
            f'<svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor"><polygon points="6 4 20 12 6 20 6 4"></polygon></svg>'
            f'</button>'
            f'<div class="player-track"><div class="player-track-fill" style="width: 0%;"></div></div>'
            f'<div class="player-time">--:--</div>'
            f'</div>'
        )

    cards_list_html.append(
        f'<details class="card-details" {open_attr}>'
        f'<summary class="card-summary">'
        f'{chevron_svg}'
        f'<span class="card-num-badge">#{idx}</span>'
        f'<span class="card-variant-title">{var_num_label}</span>'
        f'<span class="card-pill-tag">{cat_pill_label}</span>'
        f'<span class="card-views-txt">{views_s} просмотров</span>'
        f'<a href="{escaped_v_url}" target="_blank" rel="noopener noreferrer" class="card-meta-muted card-meta-muted-link" style="text-decoration: underline;">ID {html.escape(v_id)}</a>'
        f'<span class="card-meta-muted">{tc_disp}</span>'
        f'</summary>'
        f'<div class="card-expanded-body">'
        f'<div class="card-col-left">'
        f'<div class="field-label">Ссылка на TikTok</div>'
        f'<a href="{escaped_v_url}" target="_blank" rel="noopener noreferrer" class="card-tiktok-link">{escaped_v_url}</a>'
        f'<div class="card-stat-row">'
        f'<div class="card-stat-item"><div class="field-label">Опубликовано (UTC)</div><div class="mono" style="font-size: 13px; color: #ECEBE6;">{u_date}</div></div>'
        f'<div class="card-stat-item"><div class="field-label">Таймкод</div><div class="mono" style="font-size: 13px; color: #ECEBE6;">{tc_disp}</div></div>'
        f'<div class="card-stat-item"><div class="field-label">Уверенность (fuzzy)</div><div class="mono" style="font-size: 13px; color: #ECEBE6;">{conf_str}</div></div>'
        f'</div>'
        f'<div class="field-label" style="margin-top: 6px;">Расшифровка · Whisper large-v3</div>'
        f'<div class="card-transcript-box">{clean_full_escaped}</div>'
        f'</div>'
        f'<div class="card-col-right">'
        f'{player_html}'
        f'<a href="?tile={sel_tile}&demucs={v_id}" target="_self" class="demucs-btn-card">Изолировать вокал через Demucs</a>'
        f'</div>'
        f'</div>'
        f'</details>'
    )

outer_html = (
    f'<details open class="outer-cards-details">'
    f'<summary class="outer-summary">'
    f'{chevron_svg}'
    f'<span class="outer-summary-title">Карточки публикаций и аудиоплееры</span>'
    f'<span class="outer-summary-count">{active_m} шт.</span>'
    f'</summary>'
    f'<div class="outer-cards-content">'
    + ''.join(cards_list_html)
    + f'</div></details>'
)
st.markdown(clean_html(outer_html), unsafe_allow_html=True)
