import io
from typing import Optional

import pandas as pd
import pydeck as pdk
import streamlit as st

st.set_page_config(page_title="GPS Travel Visualizer", layout="wide")

# =========================================================
# PUT YOUR MAPBOX TOKEN HERE
# =========================================================
MAPBOX_TOKEN = "pk.eyJ1IjoiZmxhc2hvcDAwNyIsImEiOiJjbW44a2s5MzcwYm5vMnFzZGloMGpodDI2In0.HO3qwCL8N4YSH3PmwVc3mw"

# Default Mapbox style
MAP_STYLE = "mapbox://styles/mapbox/streets-v12"

# Accepted Excel column names
ACCEPTED_LAT_KEYS = ["lat", "latitude", "gps_lat", "gps latitude"]
ACCEPTED_LNG_KEYS = ["lng", "lon", "long", "longitude", "gps_lng", "gps longitude"]


def normalize_key(value: str) -> str:
    return " ".join(str(value).strip().lower().replace("_", " ").replace("-", " ").split())


def find_column(columns: list[str], accepted_keys: list[str]) -> Optional[str]:
    normalized_map = {normalize_key(col): col for col in columns}
    for key in accepted_keys:
        if key in normalized_map:
            return normalized_map[key]
    return None


def load_points_from_excel(file) -> pd.DataFrame:
    df = pd.read_excel(file, sheet_name=0)

    if df.empty:
        raise ValueError("Uploaded Excel file is empty.")

    lat_col = find_column(df.columns.astype(str).tolist(), ACCEPTED_LAT_KEYS)
    lng_col = find_column(df.columns.astype(str).tolist(), ACCEPTED_LNG_KEYS)

    if not lat_col or not lng_col:
        raise ValueError(
            "Required columns not found. Use headers like lat/latitude and lng/lon/longitude."
        )

    points = df[[lat_col, lng_col]].copy()
    points.columns = ["lat", "lng"]

    points["lat"] = pd.to_numeric(points["lat"], errors="coerce")
    points["lng"] = pd.to_numeric(points["lng"], errors="coerce")

    points = points.dropna(subset=["lat", "lng"])
    points = points[(points["lat"] >= -90) & (points["lat"] <= 90)]
    points = points[(points["lng"] >= -180) & (points["lng"] <= 180)]

    points = points.reset_index(drop=True)
    points["point_no"] = points.index + 1
    return points


def compute_center(points: pd.DataFrame) -> tuple[float, float]:
    if points.empty:
        return 20.5937, 78.9629
    return float(points["lat"].mean()), float(points["lng"].mean())


def estimate_zoom(points: pd.DataFrame) -> float:
    if len(points) <= 1:
        return 12

    lat_range = float(points["lat"].max() - points["lat"].min())
    lng_range = float(points["lng"].max() - points["lng"].min())
    max_range = max(lat_range, lng_range)

    if max_range <= 0.001:
        return 15
    if max_range <= 0.01:
        return 13
    if max_range <= 0.05:
        return 11
    if max_range <= 0.2:
        return 10
    if max_range <= 1:
        return 8
    if max_range <= 5:
        return 6
    return 4


def make_sample_excel() -> bytes:
    sample_df = pd.DataFrame(
        {
            "lat": [18.5204, 18.6204, 18.7204, 18.8204],
            "lng": [73.8567, 73.9267, 74.0067, 74.1067],
        }
    )

    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        sample_df.to_excel(writer, index=False, sheet_name="Sheet1")
    buffer.seek(0)
    return buffer.getvalue()


def init_state(total_points: int):
    if "play_index" not in st.session_state:
        st.session_state.play_index = 1
    if "is_playing" not in st.session_state:
        st.session_state.is_playing = False
    if "last_file_name" not in st.session_state:
        st.session_state.last_file_name = ""
    if "speed_ms" not in st.session_state:
        st.session_state.speed_ms = 800
    if "trail_points" not in st.session_state:
        st.session_state.trail_points = 10

    if total_points > 0:
        st.session_state.play_index = max(1, min(st.session_state.play_index, total_points))


def get_visible_points(points: pd.DataFrame, play_index: int, trail_points: int) -> pd.DataFrame:
    end_idx = max(1, min(play_index, len(points)))
    start_idx = max(0, end_idx - trail_points)
    return points.iloc[start_idx:end_idx].copy()


def build_map(
    all_points: pd.DataFrame,
    visible_points: pd.DataFrame,
    play_index: int,
    show_full_route: bool,
) -> pdk.Deck:
    center_lat, center_lng = compute_center(all_points)
    zoom = estimate_zoom(all_points)

    layers = []

    if show_full_route and len(all_points) >= 2:
        full_path_data = pd.DataFrame(
            {
                "path": [[row[["lng", "lat"]].tolist() for _, row in all_points.iterrows()]]
            }
        )
        full_path_layer = pdk.Layer(
            "PathLayer",
            data=full_path_data,
            get_path="path",
            get_width=3,
            width_min_pixels=2,
            get_color=[160, 160, 160, 120],
            pickable=False,
        )
        layers.append(full_path_layer)

    if len(visible_points) >= 2:
        travel_path_data = pd.DataFrame(
            {
                "path": [[row[["lng", "lat"]].tolist() for _, row in visible_points.iterrows()]]
            }
        )
        travel_path_layer = pdk.Layer(
            "PathLayer",
            data=travel_path_data,
            get_path="path",
            get_width=5,
            width_min_pixels=3,
            get_color=[0, 128, 255, 220],
            pickable=False,
        )
        layers.append(travel_path_layer)

    if not visible_points.empty:
        past_points = visible_points.iloc[:-1].copy()
        current_point = visible_points.iloc[[-1]].copy()

        if not past_points.empty:
            past_layer = pdk.Layer(
                "ScatterplotLayer",
                data=past_points,
                get_position="[lng, lat]",
                get_radius=18,
                radius_min_pixels=4,
                radius_max_pixels=8,
                pickable=True,
                stroked=True,
                filled=True,
                line_width_min_pixels=1,
                get_fill_color=[255, 165, 0, 150],
                get_line_color=[255, 255, 255, 200],
            )
            layers.append(past_layer)

        current_layer = pdk.Layer(
            "ScatterplotLayer",
            data=current_point,
            get_position="[lng, lat]",
            get_radius=28,
            radius_min_pixels=8,
            radius_max_pixels=12,
            pickable=True,
            stroked=True,
            filled=True,
            line_width_min_pixels=2,
            get_fill_color=[255, 0, 0, 220],
            get_line_color=[255, 255, 255, 255],
        )
        layers.append(current_layer)

        text_layer = pdk.Layer(
            "TextLayer",
            data=visible_points,
            get_position="[lng, lat]",
            get_text="point_no",
            get_size=14,
            get_color=[0, 0, 0, 255],
            get_alignment_baseline="bottom",
            get_pixel_offset=[0, -14],
        )
        layers.append(text_layer)

    deck = pdk.Deck(
        layers=layers,
        initial_view_state=pdk.ViewState(
            latitude=center_lat,
            longitude=center_lng,
            zoom=zoom,
            pitch=0,
        ),
        tooltip={"text": "Point {point_no}\nLat: {lat}\nLng: {lng}"},
        map_provider="mapbox",
        map_style=MAP_STYLE,
        api_keys={"mapbox": MAPBOX_TOKEN} if MAPBOX_TOKEN else None,
    )
    return deck


# ======================
# UI
# ======================

st.title("GPS Travel Visualizer")
st.caption("Upload Excel, plot GPS points, and play the route step by step.")

with st.sidebar:
    st.header("Setup")
    st.markdown("### Put token here in code")
    st.code('MAPBOX_TOKEN = "PUT_YOUR_MAPBOX_TOKEN_HERE"', language="python")

    st.markdown("### Optional map style")
    st.code('MAP_STYLE = "mapbox://styles/mapbox/streets-v12"', language="python")

    st.markdown("### Excel format")
    st.code(
        "lat,lng\n18.5204,73.8567\n18.6204,73.9267\n18.7204,74.0067",
        language="text",
    )

    st.markdown("### Accepted latitude headers")
    st.write("lat, latitude, gps_lat")

    st.markdown("### Accepted longitude headers")
    st.write("lng, lon, long, longitude, gps_lng")

if MAPBOX_TOKEN == "PUT_YOUR_MAPBOX_TOKEN_HERE" or not MAPBOX_TOKEN.strip():
    st.error("Mapbox token not added. Open app.py and replace MAPBOX_TOKEN with your real token.")
    st.stop()

uploaded_file = st.file_uploader("Upload Excel file (.xlsx or .xls)", type=["xlsx", "xls"])

sample_excel = make_sample_excel()
st.download_button(
    label="Download sample Excel file",
    data=sample_excel,
    file_name="gps_points_sample.xlsx",
    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
)

if uploaded_file is None:
    st.info("Upload an Excel file to display the route.")
    st.stop()

try:
    points = load_points_from_excel(uploaded_file)
except Exception as e:
    st.error(f"Error: {str(e)}")
    st.stop()

if points.empty:
    st.warning("No valid GPS points found in the uploaded file.")
    st.stop()

init_state(len(points))

# Reset animation when a new file is uploaded
if st.session_state.last_file_name != uploaded_file.name:
    st.session_state.last_file_name = uploaded_file.name
    st.session_state.play_index = 1
    st.session_state.is_playing = False

with st.sidebar:
    st.header("Animation Controls")

    speed_ms = st.slider(
        "Animation speed (milliseconds per step)",
        min_value=100,
        max_value=3000,
        value=st.session_state.speed_ms,
        step=100,
    )
    st.session_state.speed_ms = speed_ms

    trail_points = st.slider(
        "Visible trail points",
        min_value=1,
        max_value=min(len(points), 100),
        value=min(st.session_state.trail_points, len(points)),
        step=1,
    )
    st.session_state.trail_points = trail_points

    show_full_route = st.checkbox("Show full route in background", value=True)

    c1, c2, c3 = st.columns(3)
    if c1.button("Play", use_container_width=True):
        st.session_state.is_playing = True
    if c2.button("Pause", use_container_width=True):
        st.session_state.is_playing = False
    if c3.button("Reset", use_container_width=True):
        st.session_state.is_playing = False
        st.session_state.play_index = 1
        st.rerun()

manual_index = st.slider(
    "Travel progress point",
    min_value=1,
    max_value=len(points),
    value=st.session_state.play_index,
    step=1,
)

if manual_index != st.session_state.play_index and not st.session_state.is_playing:
    st.session_state.play_index = manual_index

visible_points = get_visible_points(
    points=points,
    play_index=st.session_state.play_index,
    trail_points=st.session_state.trail_points,
)

col1, col2, col3, col4 = st.columns(4)
col1.metric("Total Points", len(points))
col2.metric("Current Point", st.session_state.play_index)
col3.metric("Trail Size", len(visible_points))
col4.metric("Progress", f"{(st.session_state.play_index / len(points)) * 100:.1f}%")

st.subheader("Uploaded Data")
st.dataframe(points, use_container_width=True)

st.subheader("Map View")
deck = build_map(
    all_points=points,
    visible_points=visible_points,
    play_index=st.session_state.play_index,
    show_full_route=show_full_route,
)
st.pydeck_chart(deck, use_container_width=True)

current_row = points.iloc[st.session_state.play_index - 1]
st.info(
    f"Current point: {int(current_row['point_no'])} | "
    f"Latitude: {current_row['lat']:.6f} | "
    f"Longitude: {current_row['lng']:.6f}"
)

@st.fragment(run_every=0.2)
def autoplay():
    if st.session_state.is_playing:
        target_interval_ticks = max(1, int(st.session_state.speed_ms / 200))
        if "tick_counter" not in st.session_state:
            st.session_state.tick_counter = 0

        st.session_state.tick_counter += 1

        if st.session_state.tick_counter >= target_interval_ticks:
            st.session_state.tick_counter = 0
            if st.session_state.play_index < len(points):
                st.session_state.play_index += 1
                st.rerun()
            else:
                st.session_state.is_playing = False

autoplay()
