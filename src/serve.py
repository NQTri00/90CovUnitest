from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import boto3
import joblib
import os


app = FastAPI()

# Đọc tên bucket từ biến môi trường (được đặt trong systemd service)
# Sử dụng os.environ.get để tránh lỗi khi chạy cục bộ nếu chưa set
AWS_BUCKET = "mlops-lab-vinlab-0578"
AWS_MODEL_KEY = "models/latest/model.pkl"
MODEL_PATH = os.path.expanduser("~/models/model.pkl")

# Tạo thư mục chứa model nếu chưa có
os.makedirs(os.path.dirname(MODEL_PATH), exist_ok=True)


def download_model():
    """Tải file model.pkl từ S3 về máy khi server khởi động."""
    if not AWS_BUCKET:
        print("AWS_BUCKET environment variable not set. Skipping download.")
        return

    try:
        # 2.6.1: Tạo một boto3 s3 client
        s3 = boto3.client('s3')
        # 2.6.4: Tải file xuống
        s3.download_file(AWS_BUCKET, AWS_MODEL_KEY, MODEL_PATH)
        # 2.6.5: In thông báo thành công
        print(f"Model downloaded successfully from s3://{AWS_BUCKET}/{AWS_MODEL_KEY} to {MODEL_PATH}")
    except Exception as e:
        print(f"Error downloading model: {e}")
        # Nếu lỗi và chưa có model local, ta có thể thử copy từ thư mục models/ nếu đang chạy dev
        if not os.path.exists(MODEL_PATH) and os.path.exists("models/model.pkl"):
            import shutil
            shutil.copy("models/model.pkl", MODEL_PATH)
            print("Using local models/model.pkl as fallback.")


# Gọi hàm này khi module được import (chạy khi server khởi động)
download_model()

# Load model (chỉ load nếu file tồn tại)
if os.path.exists(MODEL_PATH):
    model = joblib.load(MODEL_PATH)
else:
    model = None
    print("Warning: Model file not found. Inference will not work.")


class PredictRequest(BaseModel):
    features: list[float]


@app.get("/health")
def health():
    """Endpoint kiểm tra sức khỏe server. GitHub Actions dùng endpoint này để xác nhận deploy thành công."""
    # 2.6.6: Trả về dict {"status": "ok"}
    return {"status": "ok"}


@app.post("/predict")
def predict(req: PredictRequest):
    """
    Endpoint suy luận.

    Đầu vào: JSON {"features": [f1, f2, ..., f12]}
    Đầu ra:  JSON {"prediction": <0|1|2>, "label": <"thấp"|"trung_bình"|"cao">}
    """
    if model is None:
        raise HTTPException(status_code=503, detail="Model not loaded. Please ensure model.pkl exists.")

    # 2.10.7: Kiểm tra len(req.features) == 12.
    if len(req.features) != 12:
        raise HTTPException(status_code=400, detail=f"Expected 12 features, got {len(req.features)}")

    # 2.10.8: Gọi model.predict([req.features]) để lấy kết quả dự đoán.
    try:
        prediction = int(model.predict([req.features])[0])
        
        # 2.10.9: Trả về dict chứa "prediction" (int) và "label" (string).
        #   Nhãn: 0 -> "thấp", 1 -> "trung_bình", 2 -> "cao"
        labels = {0: "thấp", 1: "trung_bình", 2: "cao"}
        label = labels.get(prediction, "unknown")
        
        return {
            "prediction": prediction,
            "label": label
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Inference error: {str(e)}")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
