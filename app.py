import io
from typing import Optional

import pandas as pd
import pydeck as pdk
import streamlit as st

st.set_page_config(page_title="GPS Lat/Lng Visualizer", layout="wide")

# =========================================================
# PUT YOUR MAPBOX TOKEN HERE
# =========================================================
MAPBOX_TOKEN = "pk.eyJ1IjoiZmxhc2hvcDAwNyIsImEiOiJjbW44a2s5MzcwYm5vMnFzZGloMGpodDI2In0.HO3qwCL8N4YSH3PmwVc3mw"

# Optional: change map style if needed
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
    elif max_range <= 0.01:
        return 13
    elif max_range <= 0.05:
        return 11
    elif max_range <= 0.2:
        return 10
    elif max_range <= 1:
        return 8
    elif max_range <= 5:
        return 6
    else:
        return 4


def build_map(points: pd.DataFrame) -> pdk.Deck:
    center_lat, center_lng = compute_center(points)
    zoom = estimate_zoom(points)

    layers = []

    if not points.empty:
        scatter_layer = pdk.Layer(
            "ScatterplotLayer",
            data=points,
            get_position="[lng, lat]",
            get_radius=20,
            radius_min_pixels=6,
            radius_max_pixels=10,
            pickable=True,
            stroked=True,
            filled=True,
            line_width_min_pixels=2,
            get_fill_color=[255, 99, 71, 180],
            get_line_color=[255, 255, 255, 220],
        )
        layers.append(scatter_layer)

        if len(points) >= 2:
            path_data = pd.DataFrame(
                {
                    "path": [[row[["lng", "lat"]].tolist() for _, row in points.iterrows()]]
                }
            )

            path_layer = pdk.Layer(
                "PathLayer",
                data=path_data,
                get_path="path",
                get_width=4,
                width_min_pixels=3,
                get_color=[0, 128, 255, 180],
                pickable=True,
            )
            layers.append(path_layer)

        text_layer = pdk.Layer(
            "TextLayer",
            data=points,
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


def make_sample_excel() -> bytes:
    sample_df = pd.DataFrame(
        {
            "lat": [18.5204, 19.0760, 18.7041],
            "lng": [73.8567, 72.8777, 73.1025],
        }
    )

    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        sample_df.to_excel(writer, index=False, sheet_name="Sheet1")
    buffer.seek(0)
    return buffer.getvalue()


# =========================================================
# UI
# =========================================================
st.title("GPS Lat/Long Visualizer")
st.caption("Upload an Excel file and visualize GPS latitude/longitude points on Mapbox.")

with st.sidebar:
    st.header("Instructions")
    st.markdown("### 1) Put token in code")
    st.code('MAPBOX_TOKEN = "PUT_YOUR_MAPBOX_TOKEN_HERE"', language="python")

    st.markdown("### 2) Excel format")
    st.code(
        "lat,lng\n18.5204,73.8567\n19.0760,72.8777\n18.7041,73.1025",
        language="text",
    )

    st.markdown("### Accepted latitude headers")
    st.write("lat, latitude, gps_lat")

    st.markdown("### Accepted longitude headers")
    st.write("lng, lon, long, longitude, gps_lng")

    st.markdown("### Map style")
    st.write(MAP_STYLE)

if MAPBOX_TOKEN == "PUT_YOUR_MAPBOX_TOKEN_HERE" or not MAPBOX_TOKEN.strip():
    st.error("Mapbox token not added. Open app.py and replace MAPBOX_TOKEN with your actual token.")
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
    st.info("Upload an Excel file to display the map.")
    st.stop()

try:
    points = load_points_from_excel(uploaded_file)
except Exception as e:
    st.error(f"Error: {str(e)}")
    st.stop()

if points.empty:
    st.warning("No valid GPS points found in the uploaded file.")
    st.stop()

col1, col2, col3 = st.columns(3)
col1.metric("Valid Points", len(points))
col2.metric("Route Segments", max(len(points) - 1, 0))
col3.metric("Center", f"{points['lat'].mean():.4f}, {points['lng'].mean():.4f}")

st.subheader("Uploaded Data")
st.dataframe(points, use_container_width=True)

st.subheader("Map View")
deck = build_map(points)
st.pydeck_chart(deck, use_container_width=True)
