<div align="center">

# 🥗 NutriPulse

### Your smart, real-time nutrition & fitness tracker

[![Live Demo](https://img.shields.io/badge/🚀_Live_Demo-nutripulse.streamlit.app-3cb371?style=for-the-badge)](https://nutripulse.streamlit.app/)
[![Python](https://img.shields.io/badge/Python-3.10+-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://python.org)
[![Streamlit](https://img.shields.io/badge/Streamlit-1.48+-FF4B4B?style=for-the-badge&logo=streamlit&logoColor=white)](https://streamlit.io)
[![USDA API](https://img.shields.io/badge/USDA-FoodData_Central-2d6a4f?style=for-the-badge)](https://fdc.nal.usda.gov/)
[![CalorieNinjas](https://img.shields.io/badge/CalorieNinjas-NLP_API-52b788?style=for-the-badge)](https://calorieninjas.com/api)

</div>

---

## ✨ What is NutriPulse?

NutriPulse is a full-featured, beautifully designed nutrition tracker built with **Streamlit** and powered by two nutrition APIs. Type natural phrases like *"2 cups white rice with carrots"* and instantly get accurate macro breakdowns, calorie tracking, exercise logging, and personalized insights — all in one clean interface.

> Built as a course project, NutriPulse demonstrates real-world API integration, data visualization, and modern UI design patterns within a Python web app.

---

## 🖼️ App Preview

| Today's Log | Insights | Profile & Goals |
|---|---|---|
| Calorie goal + macro bars | Nutrition Grade A–F | TDEE calculator |
| Water intake tracker | Nutrient radar chart | Custom macro targets |
| NLP food search | Meal composition donut | Recent foods history |
| Exercise tracker | Smart suggestions | Calorie trend chart |

---

## 🚀 Features

### 🍽️ Tab 1 — Today
| Feature | Description |
|---|---|
| **Calorie Goal** | Set a daily target; colour-coded progress bar goes green → yellow → red |
| **Macro Mini-Bars** | Live protein / carbs / fat / fiber progress vs your custom goals |
| **Water Tracker** | Log by glass, 500 ml, or 1 L; adjustable daily goal |
| **NLP Food Search** | Type *"1.5 tbsp peanut butter"* or *"bowl of oatmeal with banana"* — it just works |
| **Dual API** | CalorieNinjas NLP is primary; USDA FoodData Central is automatic fallback |
| **Inline Macros** | Full nutrition breakdown (kcal, carbs, protein, fat, fiber, sugar, sodium) visible *before* adding to log |
| **Meal Categories** | Breakfast · Lunch · Dinner · Snack — colour-coded groupings |
| **Food Log** | Grouped by meal with per-meal calorie totals + stacked macro bar |
| **Export CSV** | Download today's full log as a spreadsheet |
| **Exercise Tracker** | 10 activity types × MET-based calorie burn; net calories auto-updated |

### 📊 Tab 2 — Insights
| Feature | Description |
|---|---|
| **Nutrition Grade** | A–F letter grade based on calorie adherence, protein, fiber & macro balance |
| **Smart Suggestions** | Rule-based tips for low protein, low fiber, dehydration, over-goal calories |
| **Radar Chart** | Spider chart — today's intake vs your 5 custom nutrient targets |
| **Meal Composition** | Interactive donut chart — % of daily calories per meal type |
| **Food Comparison** | Search two foods side-by-side; grouped bar chart + diff table |

### 👤 Tab 3 — Profile & Goals
| Feature | Description |
|---|---|
| **User Profile** | Name, age, gender, weight, height, activity level |
| **TDEE Calculator** | Mifflin-St Jeor BMR × activity multiplier; one-click "Apply as goal" |
| **Custom Targets** | Set personal goals for protein, carbs, fat, and fiber |
| **Recent Foods** | Your last 10 searches for quick re-use |

### 📅 Tab 4 — History
| Feature | Description |
|---|---|
| **Daily Snapshots** | Save today's totals with one click |
| **History Table** | All saved days in a clean data table |
| **Export History** | Download full history CSV |
| **Calorie Trend** | Line chart showing calorie intake over saved days |

---

## 🛠️ Tech Stack

```
Frontend     Streamlit 1.48+   Python web framework with reactive state
Charts       Plotly             Bar, Radar, Pie, Scatter charts
Data         Pandas             DataFrame manipulation & CSV export
Styling      Custom CSS         Inter font, green gradient theme, card layout
API (Primary) CalorieNinjas     Natural language nutrition parsing
API (Fallback) USDA FoodData    380,000+ food database, relevance scoring
Math         Mifflin-St Jeor   BMR & TDEE formula for calorie recommendations
```

---

## ⚡ Quick Start

### 1. Clone the repo
```bash
git clone https://github.com/VanshikaGurbani/NutriPulse.git
cd NutriPulse
```

### 2. Install dependencies
```bash
pip install -r requirements.txt
```

### 3. Set up API keys

Create a `.env` file in the project root:
```env
USDA_API_KEY=your_usda_key_here
CALORIENINJAS_KEY=your_calorieninjas_key_here
```

| API | Free Tier | Get Key |
|---|---|---|
| USDA FoodData Central | 3,500 calls/day | [api.data.gov](https://api.data.gov/signup/) |
| CalorieNinjas | 10,000 calls/month | [calorieninjas.com/api](https://calorieninjas.com/api) |

### 4. Run the app
```bash
streamlit run nutrition_tracker.py
```

Open [http://localhost:8501](http://localhost:8501) 🎉

---

## ☁️ Deploying to Streamlit Cloud

1. Push to GitHub
2. Go to [share.streamlit.io](https://share.streamlit.io) → New app → select this repo
3. In **App settings → Secrets**, add:
```toml
USDA_API_KEY = "your_key"
CALORIENINJAS_KEY = "your_key"
```
4. Deploy — live in ~60 seconds

---

## 📁 Project Structure

```
NutriPulse/
├── nutrition_tracker.py   # Main app (backend + UI, ~750 lines)
├── requirements.txt       # Direct dependencies only
├── .streamlit/
│   └── config.toml        # Green theme configuration
├── .env                   # API keys (gitignored)
└── README.md
```

---

## 🔬 How the Food Search Works

```
User input: "2 cups white rice with carrots and peas"
         │
         ▼
  CalorieNinjas NLP API  ──► Returns each ingredient separately
  (primary)                   with quantities already parsed
         │
    No result?
         │
         ▼
  USDA FoodData Central  ──► Relevance scoring algorithm
  (fallback)                  penalises wrong-category matches
                              e.g. "Bread, oatmeal" ≠ "oatmeal"
```

The custom USDA relevance scorer uses:
- **First-token match** bonus for foods that start with the query word
- **Wrong-category penalty** (-10) for USDA "Primary, query-word" naming patterns
- **Cooked/raw** context bonus/penalty based on food type
- **Calorie sanity check** for unusually high per-100g values

---

## 🎨 Design System

- **Font:** Inter (Google Fonts)
- **Primary colour:** `#3cb371` (medium sea green)
- **Gradients:** `#2d6a4f → #40916c → #52b788`
- **Cards:** `st.container(border=True)` + custom CSS targeting `[data-testid="stVerticalBlockBorderWrapper"]`
- **Macro colours:** Calories=orange · Carbs=amber · Protein=blue · Fat=purple · Fiber=green

---

## 📜 License

MIT — free to use, modify, and distribute.

---

<div align="center">

Built with 💚 using [Streamlit](https://streamlit.io) · Data from [USDA FoodData Central](https://fdc.nal.usda.gov/) & [CalorieNinjas](https://calorieninjas.com)

**[🚀 Try it live →](https://nutripulse.streamlit.app/)**

</div>
