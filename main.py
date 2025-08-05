# main.py
from fastapi import FastAPI, HTTPException, Depends, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.middleware.cors import CORSMiddleware
from fastapi.websockets import WebSocket, WebSocketDisconnect
from pydantic import BaseModel, EmailStr
from typing import List, Optional, Dict
from datetime import datetime, timedelta
import jwt
import bcrypt
import motor.motor_asyncio
import asyncio
import json
import random
import requests
from bson import ObjectId
import os
from contextlib import asynccontextmanager


from fastapi.middleware.cors import CORSMiddleware

app = FastAPI()
from fastapi.middleware.cors import CORSMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],  # Specify your frontend URL
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Configuration
SECRET_KEY = "abc123"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30
MONGODB_URL = "mongodb://localhost:27017"
DATABASE_NAME = "trading_platform"
NEWS_API_KEY = "your-news-api-key"  # Get from newsapi.org

# Database setup
client = motor.motor_asyncio.AsyncIOMotorClient(MONGODB_URL)
database = client[DATABASE_NAME]
users_collection = database.users
orders_collection = database.orders
portfolios_collection = database.portfolios
transactions_collection = database.transactions

# WebSocket manager for real-time updates
class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []
    
    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
    
    def disconnect(self, websocket: WebSocket):
        self.active_connections.remove(websocket)
    
    async def broadcast(self, message: dict):
        for connection in self.active_connections:
            try:
                await connection.send_text(json.dumps(message))
            except:
                pass

manager = ConnectionManager()

# Pydantic models
class UserCreate(BaseModel):
    email: EmailStr
    password: str
    full_name: str

class UserLogin(BaseModel):
    email: EmailStr
    password: str

class OrderCreate(BaseModel):
    symbol: str
    quantity: int
    order_type: str  # "market" or "limit"
    side: str  # "buy" or "sell"
    price: Optional[float] = None

class Order(BaseModel):
    id: str
    user_id: str
    symbol: str
    quantity: int
    order_type: str
    side: str
    price: Optional[float]
    status: str
    created_at: datetime
    executed_at: Optional[datetime] = None

# Mock stock data
MOCK_STOCKS = {
    "AAPL": {"price": 185.00, "name": "Apple Inc."},
    "GOOGL": {"price": 2800.00, "name": "Alphabet Inc."},
    "MSFT": {"price": 380.00, "name": "Microsoft Corporation"},
    "TSLA": {"price": 250.00, "name": "Tesla Inc."},
    "AMZN": {"price": 145.00, "name": "Amazon.com Inc."},
    "NVDA": {"price": 450.00, "name": "NVIDIA Corporation"},
    "META": {"price": 320.00, "name": "Meta Platforms Inc."},
    "NFLX": {"price": 400.00, "name": "Netflix Inc."}
}

# Security
security = HTTPBearer()

def create_access_token(data: dict):
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)):
    try:
        payload = jwt.decode(credentials.credentials, SECRET_KEY, algorithms=[ALGORITHM])
        email: str = payload.get("sub")
        if email is None:
            raise HTTPException(status_code=401, detail="Invalid token")
        user = await users_collection.find_one({"email": email})
        if user is None:
            raise HTTPException(status_code=401, detail="User not found")
        return user
    except jwt.PyJWTError:
        raise HTTPException(status_code=401, detail="Invalid token")

# Price simulation task
async def simulate_price_changes():
    while True:
        for symbol in MOCK_STOCKS:
            # Simulate price changes (-2% to +2%)
            change_percent = random.uniform(-0.02, 0.02)
            MOCK_STOCKS[symbol]["price"] *= (1 + change_percent)
            MOCK_STOCKS[symbol]["price"] = round(MOCK_STOCKS[symbol]["price"], 2)
        
        # Broadcast price updates
        await manager.broadcast({
            "type": "price_update",
            "data": MOCK_STOCKS
        })
        
        await asyncio.sleep(5)  # Update every 5 seconds

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Start background task
    task = asyncio.create_task(simulate_price_changes())
    yield
    # Clean up
    task.cancel()

# FastAPI app
app = FastAPI(title="Trading Platform API", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # React dev server
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# WebSocket endpoint
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            data = await websocket.receive_text()
            # Handle incoming messages if needed
    except WebSocketDisconnect:
        manager.disconnect(websocket)

# Auth endpoints
@app.post("/auth/register")
async def register(user: UserCreate):
    print("skfhvuhdefvb")
    # Check if user exists
    existing_user = await users_collection.find_one({"email": user.email})
    if existing_user:
        raise HTTPException(status_code=400, detail="Email already registered")
    
    # Hash password
    hashed_password = bcrypt.hashpw(user.password.encode('utf-8'), bcrypt.gensalt())
    print(f"Hashed password: {hashed_password}")  # Debugging line
    
    # Create user
    user_data = {
        "email": user.email,
        "password": hashed_password,
        "full_name": user.full_name,
        "created_at": datetime.utcnow(),
        "balance": 100000.0  # Starting balance
    }
    print(user_data)
    result = await users_collection.insert_one(user_data)
    
    # Create initial portfolio
    portfolio_data = {
        "user_id": str(result.inserted_id),
        "holdings": {},
        "total_value": 100000.0,
        "cash_balance": 100000.0,
        "created_at": datetime.utcnow()
    }
    await portfolios_collection.insert_one(portfolio_data)
    
    # Generate token
    access_token = create_access_token(data={"sub": user.email})
    
    return {"access_token": access_token, "token_type": "bearer"}

@app.post("/auth/login")
async def login(user: UserLogin):
    # Find user
    db_user = await users_collection.find_one({"email": user.email})
    if not db_user:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    
    # Check password
    if not bcrypt.checkpw(user.password.encode('utf-8'), db_user["password"]):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    
    # Generate token
    access_token = create_access_token(data={"sub": user.email})
    
    return {"access_token": access_token, "token_type": "bearer"}

# Market data endpoints
@app.get("/market/stocks")
async def get_stocks():
    return MOCK_STOCKS

@app.get("/market/stock/{symbol}")
async def get_stock(symbol: str):
    if symbol not in MOCK_STOCKS:
        raise HTTPException(status_code=404, detail="Stock not found")
    return MOCK_STOCKS[symbol]

# Trading endpoints
@app.post("/orders")
async def create_order(order: OrderCreate, current_user = Depends(get_current_user)):
    if order.symbol not in MOCK_STOCKS:
        raise HTTPException(status_code=404, detail="Stock not found")
    
    # Get current portfolio
    portfolio = await portfolios_collection.find_one({"user_id": str(current_user["_id"])})
    if not portfolio:
        raise HTTPException(status_code=404, detail="Portfolio not found")
    
    current_price = MOCK_STOCKS[order.symbol]["price"]
    execution_price = order.price if order.order_type == "limit" else current_price
    total_cost = execution_price * order.quantity
    
    # Check if user has enough balance for buy orders
    if order.side == "buy" and portfolio["cash_balance"] < total_cost:
        raise HTTPException(status_code=400, detail="Insufficient balance")
    
    # Check if user has enough shares for sell orders
    if order.side == "sell":
        holdings = portfolio.get("holdings", {})
        if order.symbol not in holdings or holdings[order.symbol] < order.quantity:
            raise HTTPException(status_code=400, detail="Insufficient shares")
    
    # Create order
    order_data = {
        "user_id": str(current_user["_id"]),
        "symbol": order.symbol,
        "quantity": order.quantity,
        "order_type": order.order_type,
        "side": order.side,
        "price": order.price,
        "status": "executed",  # For MVP, execute immediately
        "created_at": datetime.utcnow(),
        "executed_at": datetime.utcnow(),
        "execution_price": execution_price
    }
    
    order_result = await orders_collection.insert_one(order_data)
    
    # Update portfolio
    holdings = portfolio.get("holdings", {})
    if order.side == "buy":
        holdings[order.symbol] = holdings.get(order.symbol, 0) + order.quantity
        new_cash_balance = portfolio["cash_balance"] - total_cost
    else:
        holdings[order.symbol] = holdings.get(order.symbol, 0) - order.quantity
        if holdings[order.symbol] == 0:
            del holdings[order.symbol]
        new_cash_balance = portfolio["cash_balance"] + total_cost
    
    # Calculate new total value
    holdings_value = sum(holdings.get(symbol, 0) * MOCK_STOCKS[symbol]["price"] 
                        for symbol in holdings)
    new_total_value = holdings_value + new_cash_balance
    
    await portfolios_collection.update_one(
        {"user_id": str(current_user["_id"])},
        {
            "$set": {
                "holdings": holdings,
                "cash_balance": new_cash_balance,
                "total_value": new_total_value,
                "updated_at": datetime.utcnow()
            }
        }
    )
    
    # Create transaction record
    transaction_data = {
        "user_id": str(current_user["_id"]),
        "order_id": str(order_result.inserted_id),
        "symbol": order.symbol,
        "quantity": order.quantity,
        "side": order.side,
        "price": execution_price,
        "total_amount": total_cost,
        "created_at": datetime.utcnow()
    }
    await transactions_collection.insert_one(transaction_data)
    
    # Broadcast order execution
    await manager.broadcast({
        "type": "order_executed",
        "data": {
            "symbol": order.symbol,
            "side": order.side,
            "quantity": order.quantity,
            "price": execution_price
        }
    })
    
    return {"message": "Order executed successfully", "order_id": str(order_result.inserted_id)}

@app.get("/orders")
async def get_orders(current_user = Depends(get_current_user)):
    orders = []
    async for order in orders_collection.find({"user_id": str(current_user["_id"])}):
        order["id"] = str(order["_id"])
        del order["_id"]
        orders.append(order)
    return orders

# Portfolio endpoints
@app.get("/portfolio")
async def get_portfolio(current_user = Depends(get_current_user)):
    portfolio = await portfolios_collection.find_one({"user_id": str(current_user["_id"])})
    if not portfolio:
        raise HTTPException(status_code=404, detail="Portfolio not found")
    
    # Calculate current values
    holdings_detail = {}
    total_holdings_value = 0
    
    for symbol, quantity in portfolio.get("holdings", {}).items():
        current_price = MOCK_STOCKS[symbol]["price"]
        value = quantity * current_price
        holdings_detail[symbol] = {
            "quantity": quantity,
            "current_price": current_price,
            "value": value,
            "name": MOCK_STOCKS[symbol]["name"]
        }
        total_holdings_value += value
    
    total_value = total_holdings_value + portfolio["cash_balance"]
    
    return {
        "holdings": holdings_detail,
        "cash_balance": portfolio["cash_balance"],
        "total_value": total_value,
        "total_holdings_value": total_holdings_value,
        "profit_loss": total_value - 100000,  # Initial balance was 100k
        "profit_loss_percent": ((total_value - 100000) / 100000) * 100
    }

@app.get("/transactions")
async def get_transactions(current_user = Depends(get_current_user)):
    transactions = []
    async for transaction in transactions_collection.find({"user_id": str(current_user["_id"])}).sort("created_at", -1):
        transaction["id"] = str(transaction["_id"])
        del transaction["_id"]
        transactions.append(transaction)
    return transactions

# News endpoints
@app.get("/news")
async def get_news():
    try:
        # If you have NewsAPI key, uncomment below and use real news
        # response = requests.get(f"https://newsapi.org/v2/everything?q=stock market&apiKey={NEWS_API_KEY}")
        # return response.json()
        
        # Mock news for MVP
        mock_news = {
            "articles": [
                {
                    "title": "Tech Stocks Rally on AI Optimism",
                    "description": "Technology stocks surged today as investors remain optimistic about AI developments.",
                    "url": "#",
                    "publishedAt": datetime.utcnow().isoformat(),
                    "source": {"name": "Mock Financial News"}
                },
                {
                    "title": "Market Volatility Expected as Fed Meeting Approaches",
                    "description": "Analysts predict increased volatility ahead of the Federal Reserve's policy announcement.",
                    "url": "#",
                    "publishedAt": (datetime.utcnow() - timedelta(hours=2)).isoformat(),
                    "source": {"name": "Mock Business Daily"}
                },
                {
                    "title": "Energy Sector Shows Strong Performance",
                    "description": "Energy stocks outperformed broader market indices today.",
                    "url": "#",
                    "publishedAt": (datetime.utcnow() - timedelta(hours=4)).isoformat(),
                    "source": {"name": "Mock Market Watch"}
                }
            ]
        }
        return mock_news
    except:
        return {"articles": []}

# Dashboard endpoint
@app.get("/dashboard")
async def get_dashboard(current_user = Depends(get_current_user)):
    # Get portfolio
    portfolio = await portfolios_collection.find_one({"user_id": str(current_user["_id"])})
    
    # Get recent transactions
    recent_transactions = []
    async for transaction in transactions_collection.find({"user_id": str(current_user["_id"])}).sort("created_at", -1).limit(5):
        transaction["id"] = str(transaction["_id"])
        del transaction["_id"]
        recent_transactions.append(transaction)
    
    # Calculate portfolio metrics
    holdings_value = 0
    for symbol, quantity in portfolio.get("holdings", {}).items():
        holdings_value += quantity * MOCK_STOCKS[symbol]["price"]
    
    total_value = holdings_value + portfolio["cash_balance"]
    
    return {
        "total_value": total_value,
        "cash_balance": portfolio["cash_balance"],
        "holdings_value": holdings_value,
        "profit_loss": total_value - 100000,
        "profit_loss_percent": ((total_value - 100000) / 100000) * 100,
        "recent_transactions": recent_transactions,
        "market_data": MOCK_STOCKS
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)