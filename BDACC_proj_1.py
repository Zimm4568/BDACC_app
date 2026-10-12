from itertools import combinations
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st


# ============================================================
# PAGE CONFIGURATION AND THEME
# ============================================================

st.set_page_config(
    page_title="F1: The Greatest of All Time?",
    page_icon="🏎️",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown(
    """
    <style>
        .stApp {
            background-color: #101116;
            color: #F4F4F5;
        }
        [data-testid="stSidebar"] {
            background-color: #191A21;
        }
        div[data-testid="stMetric"] {
            background-color: #1B1D25;
            border: 1px solid #30323C;
            padding: 16px;
            border-radius: 10px;
        }
        div[data-testid="stMetricLabel"] {
            color: #B9BBC6;
        }
        h1, h2, h3 {
            letter-spacing: -0.4px;
        }
        .hero {
            padding: 24px 0 12px 0;
        }
        .subtle {
            color: #B9BBC6;
            font-size: 0.95rem;
        }
    </style>
    """,
    unsafe_allow_html=True,
)

RED = "#E10600"
DARK = "#101116"
MUTED = "#B9BBC6"

DATA_DIR = Path(__file__).parent / "data"


# ============================================================
# DATA LOADING
# ============================================================

@st.cache_data(show_spinner="Loading Formula 1 history...")
def read_csv_file(filename):
    path = DATA_DIR / filename

    if not path.exists():
        return pd.DataFrame()

    df = pd.read_csv(path, encoding="utf-8-sig")
    df.columns = df.columns.str.strip()

    return df


@st.cache_data(show_spinner="Preparing the historical dataset...")
def load_data():
    drivers = read_csv_file("drivers.csv")
    races = read_csv_file("races.csv")
    results = read_csv_file("results.csv")
    qualifying = read_csv_file("qualifying.csv")
    standings = read_csv_file("driver_standings.csv")
    constructors = read_csv_file("constructors.csv")

    required = {
        "drivers.csv": drivers,
        "races.csv": races,
        "results.csv": results,
    }

    missing = [
        filename
        for filename, df in required.items()
        if df.empty
    ]

    if missing:
        raise FileNotFoundError(
            "Missing required CSV file(s) in the data folder: "
            + ", ".join(missing)
        )

    # Required columns
    schemas = {
        "drivers.csv": (drivers, ["driverId", "forename", "surname"]),
        "races.csv": (races, ["raceId", "year", "round"]),
        "results.csv": (
            results,
            [
                "raceId",
                "driverId",
                "constructorId",
                "positionOrder",
                "grid",
                "points",
            ],
        ),
    }

    for filename, (df, columns) in schemas.items():
        absent = [col for col in columns if col not in df.columns]
        if absent:
            raise ValueError(
                f"{filename} is missing expected columns: {absent}"
            )

    # Convert IDs and numeric fields
    for df, columns in [
        (drivers, ["driverId"]),
        (races, ["raceId", "year", "round"]),
        (
            results,
            [
                "raceId",
                "driverId",
                "constructorId",
                "positionOrder",
                "grid",
                "points",
            ],
        ),
        (qualifying, ["raceId", "driverId", "position"]),
        (standings, ["raceId", "driverId", "position", "points"]),
    ]:
        for col in columns:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce")

    drivers["driverName"] = (
        drivers["forename"].fillna("").astype(str)
        + " "
        + drivers["surname"].fillna("").astype(str)
    ).str.strip()

    if "nationality" not in drivers.columns:
        drivers["nationality"] = "Unknown"

    # Remove malformed records
    races = races.dropna(subset=["raceId", "year"])
    results = results.dropna(subset=["raceId", "driverId"])

    return {
        "drivers": drivers,
        "races": races,
        "results": results,
        "qualifying": qualifying,
        "standings": standings,
        "constructors": constructors,
    }


# ============================================================
# CHAMPIONSHIP CALCULATION
# ============================================================

def get_champions(standings, races, drivers):
    """
    Find each season's champion using the standings
    recorded after the last scheduled race in that season.

    This avoids counting the same championship once per race.
    """
    if standings.empty or "position" not in standings.columns:
        return pd.DataFrame(
            columns=["year", "driverId", "driverName"]
        )

    race_cols = ["raceId", "year", "round"]
    race_info = races[race_cols].dropna(subset=["raceId", "year"])

    last_races = (
        race_info.sort_values(["year", "round", "raceId"])
        .drop_duplicates("year", keep="last")
    )

    final_standings = standings.merge(
        last_races[["raceId", "year"]],
        on="raceId",
        how="inner",
    )

    final_standings["position"] = pd.to_numeric(
        final_standings["position"], errors="coerce"
    )

    champions = final_standings[
        final_standings["position"] == 1
    ].copy()

    champions = champions.merge(
        drivers[["driverId", "driverName"]],
        on="driverId",
        how="left",
    )

    return champions[
        ["year", "driverId", "driverName"]
    ].drop_duplicates("year")


# ============================================================
# TEAMMATE HEAD-TO-HEAD
# ============================================================

def calculate_teammate_records(results):
    """
    Compare drivers who raced for the same constructor
    in the same Grand Prix.

    A lower positionOrder means a better classified result.
    A tie contributes half a win to each driver.

    This is a simplified comparison, not a causal estimate
    of driver skill or equal-car performance.
    """
    columns = [
        "driverId",
        "teammate_comparisons",
        "teammate_points",
        "teammate_score",
    ]

    if results.empty:
        return pd.DataFrame(columns=columns)

    required = [
        "raceId",
        "driverId",
        "constructorId",
        "positionOrder",
    ]

    if any(col not in results.columns for col in required):
        return pd.DataFrame(columns=columns)

    eligible = results.dropna(
        subset=[
            "raceId",
            "driverId",
            "constructorId",
            "positionOrder",
        ]
    )

    eligible = eligible.drop_duplicates(
        ["raceId", "driverId", "constructorId"]
    )

    comparison_counts = {}
    comparison_points = {}

    for _, group in eligible.groupby(
        ["raceId", "constructorId"],
        sort=False,
    ):
        if len(group) < 2:
            continue

        rows = group[
            ["driverId", "positionOrder"]
        ].to_dict("records")

        for a, b in combinations(rows, 2):
            driver_a = int(a["driverId"])
            driver_b = int(b["driverId"])

            pos_a = float(a["positionOrder"])
            pos_b = float(b["positionOrder"])

            comparison_counts[driver_a] = (
                comparison_counts.get(driver_a, 0) + 1
            )
            comparison_counts[driver_b] = (
                comparison_counts.get(driver_b, 0) + 1
            )

            if pos_a < pos_b:
                points_a, points_b = 1.0, 0.0
            elif pos_b < pos_a:
                points_a, points_b = 0.0, 1.0
            else:
                points_a, points_b = 0.5, 0.5

            comparison_points[driver_a] = (
                comparison_points.get(driver_a, 0.0)
                + points_a
            )
            comparison_points[driver_b] = (
                comparison_points.get(driver_b, 0.0)
                + points_b
            )

    output = []

    for driver_id, count in comparison_counts.items():
        points = comparison_points[driver_id]

        output.append(
            {
                "driverId": driver_id,
                "teammate_comparisons": count,
                "teammate_points": points,
                "teammate_score": points / count,
            }
        )

    return pd.DataFrame(output, columns=columns)


# ============================================================
# BUILD CAREER AND SEASON METRICS
# ============================================================

def calculate_metrics(data, start_year, end_year):
    drivers = data["drivers"]
    races = data["races"]
    results = data["results"]
    qualifying = data["qualifying"]
    standings = data["standings"]

    race_info = races[
        ["raceId", "year", "round"]
    ].drop_duplicates("raceId")

    # Attach the season to each Grand Prix result
    race_results = results.merge(
        race_info,
        on="raceId",
        how="inner",
    )

    race_results = race_results[
        race_results["year"].between(start_year, end_year)
    ].copy()

    race_results = race_results.merge(
        drivers[["driverId", "driverName", "nationality"]],
        on="driverId",
        how="left",
    )

    race_results["positionOrder"] = pd.to_numeric(
        race_results["positionOrder"], errors="coerce"
    )
    race_results["points"] = pd.to_numeric(
        race_results["points"], errors="coerce"
    )
    race_results["grid"] = pd.to_numeric(
        race_results["grid"], errors="coerce"
    )

    # Career results in the selected year window
    career = (
        race_results.groupby(
            ["driverId", "driverName", "nationality"],
            as_index=False,
        )
        .agg(
            starts=("raceId", "count"),
            wins=(
                "positionOrder",
                lambda x: (x == 1).sum(),
            ),
            podiums=(
                "positionOrder",
                lambda x: x.between(1, 3).sum(),
            ),
            avg_finish=("positionOrder", "mean"),
            total_points=("points", "sum"),
            seasons=("year", "nunique"),
            first_year=("year", "min"),
            last_year=("year", "max"),
        )
    )

    career["win_rate"] = career["wins"] / career["starts"]
    career["podium_rate"] = (
        career["podiums"] / career["starts"]
    )

    # Championship counts
    champions = get_champions(
        standings, races, drivers
    )

    champions = champions[
        champions["year"].between(start_year, end_year)
    ]

    title_counts = (
        champions.groupby("driverId")
        .size()
        .rename("titles")
        .reset_index()
    )

    career = career.merge(
        title_counts,
        on="driverId",
        how="left",
    )

    career["titles"] = career["titles"].fillna(0).astype(int)
    career["title_rate"] = (
        career["titles"] / career["seasons"].replace(0, np.nan)
    )

    # Qualifying statistics
    if (
        not qualifying.empty
        and {"raceId", "driverId", "position"}.issubset(
            qualifying.columns
        )
    ):
        quali = qualifying.merge(
            race_info,
            on="raceId",
            how="inner",
        )

        quali = quali[
            quali["year"].between(start_year, end_year)
        ].copy()

        quali["position"] = pd.to_numeric(
            quali["position"], errors="coerce"
        )

        quali = quali.dropna(
            subset=["driverId", "position"]
        )

        quali_metrics = (
            quali.groupby("driverId", as_index=False)
            .agg(
                qualifying_appearances=("position", "count"),
                poles=(
                    "position",
                    lambda x: (x == 1).sum(),
                ),
                avg_quali=("position", "mean"),
            )
        )

        quali_metrics["pole_rate"] = (
            quali_metrics["poles"]
            / quali_metrics["qualifying_appearances"]
        )

        career = career.merge(
            quali_metrics,
            on="driverId",
            how="left",
        )
    else:
        career["qualifying_appearances"] = 0
        career["poles"] = 0
        career["avg_quali"] = np.nan
        career["pole_rate"] = np.nan

    # Teammate comparisons within the selected period
    teammate = calculate_teammate_records(race_results)

    career = career.merge(
        teammate,
        on="driverId",
        how="left",
    )

    career["teammate_comparisons"] = (
        career["teammate_comparisons"].fillna(0)
    )
    career["teammate_score"] = career["teammate_score"].fillna(
        np.nan
    )

    # Driver-season summary for the historical timeline
    season_summary = (
        race_results.groupby(
            ["year", "driverId", "driverName"],
            as_index=False,
        )
        .agg(
            wins=(
                "positionOrder",
                lambda x: (x == 1).sum(),
            ),
            podiums=(
                "positionOrder",
                lambda x: x.between(1, 3).sum(),
            ),
            points=("points", "sum"),
            starts=("raceId", "count"),
        )
    )

    return career, season_summary, champions, race_results


# ============================================================
# GREATNESS INDEX
# ============================================================

def build_ranking(career, weights):
    """
    Convert selected metrics to percentile scores, then
    combine them with user-adjustable weights.

    Percentiles are relative to the drivers currently included
    in the ranking. This is a configurable index, not an
    objective measurement of the greatest driver.
    """
    ranking = career.copy()

    metric_definitions = {
        "Championships": ("titles", True),
        "Win rate": ("win_rate", True),
        "Podium rate": ("podium_rate", True),
        "Qualifying": ("avg_quali", False),
        "Teammate record": ("teammate_score", True),
    }

    score_columns = []

    for label, (column, higher_is_better) in (
        metric_definitions.items()
    ):
        score_col = f"score_{label}"

        if column not in ranking.columns:
            ranking[score_col] = 50.0
        else:
            values = ranking[column]

            if values.notna().sum() == 0:
                ranking[score_col] = 50.0
            else:
                ranking[score_col] = (
                    values.rank(
                        pct=True,
                        ascending=not higher_is_better,
                    )
                    * 100
                ).fillna(50.0)

        score_columns.append(score_col)

    total_weight = sum(weights.values())

    if total_weight <= 0:
        ranking["greatness_score"] = np.nan
        return ranking

    weighted_score = 0.0

    for label, weight in weights.items():
        weighted_score += (
            ranking[f"score_{label}"] * weight
        )

    ranking["greatness_score"] = (
        weighted_score / total_weight
    )

    ranking = ranking.sort_values(
        ["greatness_score", "titles", "wins"],
        ascending=[False, False, False],
    ).reset_index(drop=True)

    ranking["rank"] = np.arange(1, len(ranking) + 1)

    return ranking


# ============================================================
# LOAD DATA AND HANDLE ERRORS
# ============================================================

try:
    data = load_data()
except (FileNotFoundError, ValueError, pd.errors.ParserError) as exc:
    st.error("Could not load the Formula 1 dataset.")
    st.markdown(
        """
        Check that `drivers.csv`, `races.csv`, and
        `results.csv` are inside the `data/` folder.

        Confirm that the files use the expected TracingInsights
        column names.
        """
    )
    st.code(str(exc))
    st.stop()

if data["races"].empty or data["results"].empty:
    st.error("The race or results dataset is empty.")
    st.stop()

min_available_year = int(data["races"]["year"].min())
max_available_year = int(data["races"]["year"].max())


# ============================================================
# SIDEBAR
# ============================================================

st.sidebar.title("🏎️ F1 Explorer")
st.sidebar.caption("Explore the history of Formula 1")

st.sidebar.subheader("Historical period")

year_range = st.sidebar.slider(
    "Seasons",
    min_value=min_available_year,
    max_value=max_available_year,
    value=(min_available_year, max_available_year),
)

start_year, end_year = year_range

st.sidebar.divider()

st.sidebar.subheader("Ranking eligibility")

min_starts = st.sidebar.slider(
    "Minimum Grand Prix starts",
    min_value=1,
    max_value=100,
    value=20,
    help=(
        "Exclude drivers with very short careers from "
        "the ranking. Career metrics still use the selected "
        "historical period."
    ),
)

st.sidebar.caption(
    "The minimum-start filter affects the ranking and "
    "comparison shortlist."
)


# ============================================================
# CALCULATE THE CURRENT VIEW
# ============================================================

career, season_summary, champions, race_results = (
    calculate_metrics(data, start_year, end_year)
)

eligible_career = career[
    career["starts"] >= min_starts
].copy()

if eligible_career.empty:
    st.warning(
        "No drivers meet the minimum-start requirement "
        "for the selected seasons. Expand the date range "
        "or reduce the minimum number of starts."
    )
    st.stop()


# ============================================================
# HEADER
# ============================================================

st.markdown(
    """
    <div class="hero">
        <h1>THE GREATEST FORMULA 1 DRIVER?</h1>
        <p class="subtle">
            75+ years of racing history. Different generations.
            One question: what does greatness really mean?
        </p>
    </div>
    """,
    unsafe_allow_html=True,
)

st.caption(
    f"Data period: {start_year}–{end_year} · "
    f"Grand Prix results only for race statistics"
)


# ============================================================
# TABS
# ============================================================

overview_tab, ranking_tab, compare_tab, history_tab, data_tab = (
    st.tabs(
        [
            "🏁 Overview",
            "🏆 GOAT Ranking",
            "⚔️ Driver Comparison",
            "📈 F1 Through Time",
            "📋 Data Explorer",
        ]
    )
)


# ============================================================
# OVERVIEW
# ============================================================

with overview_tab:
    total_races = race_results["raceId"].nunique()
    total_drivers = race_results["driverId"].nunique()
    total_wins = int(
        (race_results["positionOrder"] == 1).sum()
    )
    total_titles = champions["year"].nunique()

    m1, m2, m3, m4 = st.columns(4)

    m1.metric("Grand Prix events", f"{total_races:,}")
    m2.metric("Drivers represented", f"{total_drivers:,}")
    m3.metric("Race wins recorded", f"{total_wins:,}")
    m4.metric("Championship seasons", f"{total_titles:,}")

    st.divider()

    left, right = st.columns([1.4, 1])

    with left:
        st.subheader("Who won the most races?")

        top_winners = (
            eligible_career.sort_values(
                ["wins", "win_rate"],
                ascending=False,
            )
            .head(12)
            .sort_values("wins")
        )

        fig = px.bar(
            top_winners,
            x="wins",
            y="driverName",
            orientation="h",
            text="wins",
            color="wins",
            color_continuous_scale=["#7A0B0B", RED],
            labels={
                "wins": "Grand Prix wins",
                "driverName": "",
            },
        )

        fig.update_layout(
            template="plotly_dark",
            paper_bgcolor=DARK,
            plot_bgcolor=DARK,
            coloraxis_showscale=False,
            margin=dict(l=10, r=10, t=20, b=20),
            yaxis_title="",
            xaxis_title="Career wins in selected period",
        )

        st.plotly_chart(fig, use_container_width=True)

    with right:
        st.subheader("Championship leaders")

        title_leaders = (
            champions.groupby("driverName")
            .size()
            .rename("Championships")
            .reset_index()
            .sort_values("Championships", ascending=False)
            .head(10)
        )

        if not title_leaders.empty:
            fig = px.bar(
                title_leaders.sort_values("Championships"),
                x="Championships",
                y="driverName",
                orientation="h",
                text="Championships",
                color_discrete_sequence=[RED],
                labels={"driverName": ""},
            )

            fig.update_layout(
                template="plotly_dark",
                paper_bgcolor=DARK,
                plot_bgcolor=DARK,
                margin=dict(l=10, r=10, t=20, b=20),
                yaxis_title="",
            )

            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info(
                "Championship standings are unavailable "
                "for this selection."
            )

    st.divider()

    st.subheader("What makes a driver great?")

    st.markdown(
        """
        **Titles** reward season-long success. **Win rate**
        measures how often a driver converts a start into a
        victory. **Podium rate** measures consistency near the
        front. **Qualifying** captures one-lap performance.
        **Teammate record** compares classified results among
        drivers sharing a constructor in the same Grand Prix.

        These measures capture different aspects of performance.
        No single metric accounts perfectly for car quality,
        reliability, rules, or the strength of the competition.
        """
    )


# ============================================================
# GOAT RANKING
# ============================================================

with ranking_tab:
    st.subheader("Build your own all-time ranking")

    st.write(
        "Adjust the weights to decide what matters most. "
        "The index ranks drivers relative to the eligible "
        "drivers in the selected period."
    )

    c1, c2, c3 = st.columns(3)
    c4, c5 = st.columns(2)

    with c1:
        championship_weight = st.slider(
            "Championships",
            0, 100, 30,
            key="w_championships",
        )

    with c2:
        win_weight = st.slider(
            "Win rate",
            0, 100, 25,
            key="w_win",
        )

    with c3:
        podium_weight = st.slider(
            "Podium rate",
            0, 100, 15,
            key="w_podium",
        )

    with c4:
        qualifying_weight = st.slider(
            "Qualifying performance",
            0, 100, 15,
            key="w_qualifying",
        )

    with c5:
        teammate_weight = st.slider(
            "Teammate record",
            0, 100, 15,
            key="w_teammate",
        )

    weights = {
        "Championships": championship_weight,
        "Win rate": win_weight,
        "Podium rate": podium_weight,
        "Qualifying": qualifying_weight,
        "Teammate record": teammate_weight,
    }

    if sum(weights.values()) == 0:
        st.warning("Set at least one weight above zero.")
    else:
        ranking = build_ranking(eligible_career, weights)

        st.caption(
            "Each metric is converted to a percentile score "
            "before weighting. Missing qualifying or teammate "
            "scores receive a neutral 50-point score. This is "
            "a modeling choice, not evidence of average ability."
        )

        top_n = st.slider(
            "Drivers to show",
            min_value=5,
            max_value=min(30, len(ranking)),
            value=min(15, len(ranking)),
        )

        top_ranking = ranking.head(top_n).copy()

        st.subheader("Greatness index leaderboard")

        fig = px.bar(
            top_ranking.sort_values("greatness_score"),
            x="greatness_score",
            y="driverName",
            orientation="h",
            text=top_ranking.sort_values(
                "greatness_score"
            )["greatness_score"].map(
                lambda x: f"{x:.1f}"
            ),
            color="greatness_score",
            color_continuous_scale=["#7A0B0B", RED],
            labels={
                "greatness_score": "Weighted index (0–100)",
                "driverName": "",
            },
        )

        fig.update_layout(
            template="plotly_dark",
            paper_bgcolor=DARK,
            plot_bgcolor=DARK,
            coloraxis_showscale=False,
            margin=dict(l=10, r=10, t=20, b=20),
            yaxis_title="",
        )

        st.plotly_chart(fig, use_container_width=True)

        st.subheader("Ranking details")

        display_columns = [
            "rank",
            "driverName",
            "nationality",
            "starts",
            "titles",
            "wins",
            "win_rate",
            "podiums",
            "podium_rate",
            "avg_quali",
            "teammate_score",
            "greatness_score",
        ]

        ranking_display = ranking[display_columns].copy()

        ranking_display["win_rate"] = (
            ranking_display["win_rate"] * 100
        ).round(1)

        ranking_display["podium_rate"] = (
            ranking_display["podium_rate"] * 100
        ).round(1)

        ranking_display["teammate_score"] = (
            ranking_display["teammate_score"] * 100
        ).round(1)

        ranking_display["avg_quali"] = (
            ranking_display["avg_quali"].round(2)
        )

        ranking_display["greatness_score"] = (
            ranking_display["greatness_score"].round(2)
        )

        ranking_display = ranking_display.rename(
            columns={
                "rank": "Rank",
                "driverName": "Driver",
                "nationality": "Nationality",
                "starts": "Starts",
                "titles": "Titles",
                "wins": "Wins",
                "win_rate": "Win rate (%)",
                "podiums": "Podiums",
                "podium_rate": "Podium rate (%)",
                "avg_quali": "Avg qualifying position",
                "teammate_score": "Teammate score (%)",
                "greatness_score": "Greatness index",
            }
        )

        st.dataframe(
            ranking_display,
            use_container_width=True,
            hide_index=True,
        )

        csv = ranking_display.to_csv(index=False).encode("utf-8")

        st.download_button(
            "Download ranking as CSV",
            data=csv,
            file_name="f1_goat_ranking.csv",
            mime="text/csv",
        )


# ============================================================
# DRIVER COMPARISON
# ============================================================

with compare_tab:
    st.subheader("Compare two careers")

    comparison_pool = eligible_career.sort_values(
        "driverName"
    )

    driver_names = comparison_pool["driverName"].tolist()

    default_a = (
        "Lewis Hamilton"
        if "Lewis Hamilton" in driver_names
        else driver_names[0]
    )

    default_b = (
        "Michael Schumacher"
        if "Michael Schumacher" in driver_names
        else driver_names[min(1, len(driver_names) - 1)]
    )

    col_a, col_b = st.columns(2)

    with col_a:
        driver_a_name = st.selectbox(
            "Driver A",
            driver_names,
            index=driver_names.index(default_a),
            key="compare_a",
        )

    with col_b:
        driver_b_name = st.selectbox(
            "Driver B",
            driver_names,
            index=driver_names.index(default_b),
            key="compare_b",
        )

    driver_a = comparison_pool[
        comparison_pool["driverName"] == driver_a_name
    ].iloc[0]

    driver_b = comparison_pool[
        comparison_pool["driverName"] == driver_b_name
    ].iloc[0]

    a, b = st.columns(2)

    with a:
        st.markdown(f"### {driver_a_name}")
        st.metric("World championships", int(driver_a["titles"]))
        st.metric("Grand Prix wins", int(driver_a["wins"]))
        st.metric(
            "Win rate",
            f"{driver_a['win_rate'] * 100:.1f}%",
        )
        st.metric(
            "Podium rate",
            f"{driver_a['podium_rate'] * 100:.1f}%",
        )

    with b:
        st.markdown(f"### {driver_b_name}")
        st.metric("World championships", int(driver_b["titles"]))
        st.metric("Grand Prix wins", int(driver_b["wins"]))
        st.metric(
            "Win rate",
            f"{driver_b['win_rate'] * 100:.1f}%",
        )
        st.metric(
            "Podium rate",
            f"{driver_b['podium_rate'] * 100:.1f}%",
        )

    st.divider()

    compare_metrics = pd.DataFrame(
        {
            "Metric": [
                "Championships",
                "Win rate (%)",
                "Podium rate (%)",
                "Pole rate (%)",
                "Teammate score (%)",
            ],
            driver_a_name: [
                driver_a["titles"],
                driver_a["win_rate"] * 100,
                driver_a["podium_rate"] * 100,
                driver_a["pole_rate"] * 100
                if pd.notna(driver_a["pole_rate"])
                else np.nan,
                driver_a["teammate_score"] * 100
                if pd.notna(driver_a["teammate_score"])
                else np.nan,
            ],
            driver_b_name: [
                driver_b["titles"],
                driver_b["win_rate"] * 100,
                driver_b["podium_rate"] * 100,
                driver_b["pole_rate"] * 100
                if pd.notna(driver_b["pole_rate"])
                else np.nan,
                driver_b["teammate_score"] * 100
                if pd.notna(driver_b["teammate_score"])
                else np.nan,
            ],
        }
    )

    compare_long = compare_metrics.melt(
        id_vars="Metric",
        var_name="Driver",
        value_name="Value",
    )

    fig = px.bar(
        compare_long,
        x="Metric",
        y="Value",
        color="Driver",
        barmode="group",
        color_discrete_sequence=[RED, "#8A8D98"],
        labels={"Value": "Value", "Metric": ""},
    )

    fig.update_layout(
        template="plotly_dark",
        paper_bgcolor=DARK,
        plot_bgcolor=DARK,
        margin=dict(l=10, r=10, t=20, b=20),
        legend_title_text="",
    )

    st.plotly_chart(fig, use_container_width=True)

    st.caption(
        "Rates use the selected seasons. Teammate scores "
        "compare classified finishing order in races where "
        "the drivers shared a constructor with teammates. "
        "A comparison between two different drivers here is "
        "not a direct head-to-head unless they were teammates."
    )


# ============================================================
# F1 THROUGH TIME
# ============================================================

with history_tab:
    st.subheader("How Formula 1 changed through the decades")

    if season_summary.empty:
        st.info("No seasonal data is available.")
    else:
        trend_options = {
            "Race wins": "wins",
            "Podiums": "podiums",
            "Championship points": "points",
        }

        selected_trend = st.selectbox(
            "Historical measure",
            list(trend_options.keys()),
        )

        trend_column = trend_options[selected_trend]

        # Identify drivers with the most of the selected metric
        top_drivers = (
            season_summary.groupby("driverName")[trend_column]
            .sum()
            .sort_values(ascending=False)
            .head(8)
            .index.tolist()
        )

        trend_data = season_summary[
            season_summary["driverName"].isin(top_drivers)
        ].copy()

        fig = px.line(
            trend_data,
            x="year",
            y=trend_column,
            color="driverName",
            markers=True,
            labels={
                "year": "Season",
                trend_column: selected_trend,
                "driverName": "Driver",
            },
        )

        fig.update_layout(
            template="plotly_dark",
            paper_bgcolor=DARK,
            plot_bgcolor=DARK,
            margin=dict(l=10, r=10, t=20, b=20),
        )

        st.plotly_chart(fig, use_container_width=True)

        st.caption(
            "Points are not directly comparable across all eras "
            "because scoring systems and the number of races "
            "per season have changed."
        )

    st.divider()

    st.subheader("World champions by season")

    if not champions.empty:
        champions_chart = champions.sort_values("year").copy()

        fig = px.scatter(
            champions_chart,
            x="year",
            y="driverName",
            color="driverName",
            hover_data=["year"],
            labels={
                "year": "Championship season",
                "driverName": "World champion",
            },
        )

        fig.update_layout(
            template="plotly_dark",
            paper_bgcolor=DARK,
            plot_bgcolor=DARK,
            showlegend=False,
            margin=dict(l=10, r=10, t=20, b=20),
        )

        st.plotly_chart(fig, use_container_width=True)

        st.dataframe(
            champions.sort_values("year", ascending=False),
            use_container_width=True,
            hide_index=True,
        )
    else:
        st.info(
            "No championship data is available for this period."
        )


# ============================================================
# DATA EXPLORER
# ============================================================

with data_tab:
    st.subheader("Explore the underlying data")

    table_choice = st.selectbox(
        "Choose a dataset",
        [
            "Driver career statistics",
            "Race results",
            "Season summaries",
            "Championship winners",
        ],
    )

    if table_choice == "Driver career statistics":
        selected_table = career.copy()

    elif table_choice == "Race results":
        selected_table = race_results.copy()

    elif table_choice == "Season summaries":
        selected_table = season_summary.copy()

    else:
        selected_table = champions.copy()

    st.write(f"Records: {len(selected_table):,}")

    st.dataframe(
        selected_table,
        use_container_width=True,
        hide_index=True,
    )

    export = selected_table.to_csv(index=False).encode("utf-8")

    st.download_button(
        "Download this table as CSV",
        data=export,
        file_name="f1_explorer_data.csv",
        mime="text/csv",
    )

    st.divider()

    st.subheader("Data sources and methodology")

    st.markdown(
        """
        **Data:** TracingInsights Formula 1 Race Data archive.

        **Race results:** Career starts, wins, podiums, and
        finishing-position statistics are calculated from
        the Grand Prix results table.

        **Championships:** A driver is counted as champion when
        their position in the final recorded standings of a
        season is first.

        **Qualifying:** Pole positions and average qualifying
        position are based on qualifying records available
        for the selected period.

        **Teammate record:** Classified results are compared
        for drivers who shared a constructor in a Grand Prix.
        Each pairwise comparison awards one point for a better
        position, zero for a worse position, and half a point
        to each driver for a tie.

        **Greatness index:** Each selected metric is converted
        to a percentile across the eligible drivers, then
        combined according to the weights chosen by the user.
        The ranking is exploratory, not an objective verdict
        on the greatest driver in Formula 1 history.
        """
    )

    st.markdown(
        "[TracingInsights RaceData on GitHub]"
        "(https://github.com/TracingInsights/RaceData)"
    )

    st.caption(
        "This is an independent fan project and is not affiliated "
        "with Formula 1, the FIA, or any racing team."
    )