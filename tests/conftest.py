import copy
import pytest


@pytest.fixture
def cfg():
    return {
        "input":{"path":"unused.csv", "frequency":"D"},
        "output":{"directory":"unused", "interactive_html":False},
        "calendar":{"active_weekdays":list(range(7)), "active_hours":list(range(8,19))},
        "metrics":{
            "wash_count":{"aggregation":"sum", "detector":"poisson"},
            "revenue":{"aggregation":"sum", "detector":"zscore"},
            "operating_income":{"aggregation":"sum", "detector":"zscore"},
            "conversion_rate":{"aggregation":"ratio", "numerator":"wash_count", "denominator":"revenue", "multiplier":100, "detector":"zscore"},
        },
        "analysis":{
            "frequencies":["D","W-SUN","MS"],
            "windows":{"D":{"short":2,"long":4},"W-SUN":{"short":2,"long":4},"MS":{"short":2,"long":4}},
            "z_threshold":3.0,"poisson_alpha":.01,"min_history_fraction":1.0,
            "cusum":{"enabled":True,"horizon":"long","k":.5,"h":5.0,"score_cap":2.0},
        },
    }
