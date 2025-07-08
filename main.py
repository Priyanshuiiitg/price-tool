from fastapi import FastAPI
import uvicorn
from src.api.routes import router

app = FastAPI(
    title="Product Price Comparison API",
    description="A tool that fetches prices of products from multiple websites based on the country",
    version="1.0.0",
)

app.include_router(router)

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True) 