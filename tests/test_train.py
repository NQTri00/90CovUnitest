import os
import json
import numpy as np
import pandas as pd
from src.train import train


FEATURE_NAMES = [
    "fixed_acidity", "volatile_acidity", "citric_acid", "residual_sugar",
    "chlorides", "free_sulfur_dioxide", "total_sulfur_dioxide", "density",
    "pH", "sulphates", "alcohol", "wine_type",
]


def _make_temp_data(tmp_path):
    """
    Tao dataset nho voi cung schema Wine Quality de su dung trong test.

    pytest cung cap `tmp_path` la mot thu muc tam thoi, tu dong duoc xoa sau khi test ket thuc.
    """
    rng = np.random.default_rng(0)
    n = 200
    # 2.10.1: Tao mang X co kich thuoc (n, len(FEATURE_NAMES)) voi gia tri ngau nhien [0, 1)
    X = rng.random((n, len(FEATURE_NAMES)))
    # 2.10.2: Tao mang y co n phan tu, moi phan tu la so nguyen ngau nhien trong [0, 3)
    y = rng.integers(0, 3, size=n)
    # 2.10.3: Tao DataFrame tu X voi cac cot la FEATURE_NAMES, them cot "target" = y
    df = pd.DataFrame(X, columns=FEATURE_NAMES)
    df["target"] = y
    # 2.10.4: Luu 160 dong dau vao file train.csv va 40 dong cuoi vao file eval.csv tai tmp_path
    train_path = tmp_path / "train.csv"
    eval_path = tmp_path / "eval.csv"
    df.iloc[:160].to_csv(train_path, index=False)
    df.iloc[160:].to_csv(eval_path, index=False)
    # 2.10.5: Tra ve (train_path, eval_path)
    return str(train_path), str(eval_path)


def test_train_returns_float(tmp_path):
    """Kiem tra ham train() tra ve mot so thuc trong khoang [0, 1]."""
    train_path, eval_path = _make_temp_data(tmp_path)
    # 2.10.6: Goi ham train() voi sieu tham so nho (n_estimators=10, max_depth=3)
    acc = train(
        {"n_estimators": 10, "max_depth": 3},
        data_path=train_path,
        eval_path=eval_path
    )
    # 2.10.7: assert ket qua tra ve la float va nam trong [0.0, 1.0]
    assert isinstance(acc, float)
    assert 0.0 <= acc <= 1.0


def test_metrics_file_created(tmp_path):
    """Kiem tra file outputs/metrics.json duoc tao sau khi huan luyen."""
    train_path, eval_path = _make_temp_data(tmp_path)
    train(
        {"n_estimators": 10, "max_depth": 3},
        data_path=train_path,
        eval_path=eval_path,
    )
    # 2.10.8: assert file "outputs/metrics.json" ton tai
    assert os.path.exists("outputs/metrics.json")
    # 2.10.9: Doc file metrics.json va assert no chua ca "accuracy" va "f1_score"
    with open("outputs/metrics.json") as f:
        metrics = json.load(f)
    assert "accuracy" in metrics
    assert "f1_score" in metrics


def test_model_file_created(tmp_path):
    """Kiem tra file models/model.pkl duoc tao sau khi huan luyen."""
    train_path, eval_path = _make_temp_data(tmp_path)
    train(
        {"n_estimators": 10, "max_depth": 3},
        data_path=train_path,
        eval_path=eval_path,
    )
    # 2.10.10: assert file "models/model.pkl" ton tai
    assert os.path.exists("models/model.pkl")
