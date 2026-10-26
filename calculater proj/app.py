"""Compatibility entry point for the existing Streamlit Cloud deployment."""

from pathlib import Path
import runpy


TARGET = Path(__file__).resolve().parents[1] / "Financial-Analysis-Toolkit" / "apps" / "streamlit_app.py"
runpy.run_path(str(TARGET), run_name="__main__")
