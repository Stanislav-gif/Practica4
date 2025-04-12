from fastapi import FastAPI, HTTPException, Depends, Query
from pydantic import BaseModel
from sqlalchemy import create_engine, Column, Integer, String
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session
from typing import List, Optional

# Настройка базы данных
DATABASE_URL = "sqlite:///./energy_drinks.db"

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# Модель базы данных
class EnergyDrink(Base):
    __tablename__ = "energy_drinks"
    id = Column(Integer, primary_key=True, index=True)
    brand = Column(String, index=True) 
    name = Column(String)              
    price = Column(Integer)            

Base.metadata.create_all(bind=engine)

# Модели Pydantic для валидации
class EnergyDrinkCreate(BaseModel):
    brand: str
    name: str
    price: int

class EnergyDrinkUpdate(BaseModel):
    brand: Optional[str] = None
    name: Optional[str] = None
    price: Optional[int] = None

class EnergyDrinkResponse(BaseModel):
    id: int
    brand: str
    name: str
    price: int

    class Config:
        from_attributes = True

class EnergyDrinkRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_all(self, skip: int = 0, limit: int = 10, sort_by: Optional[str] = None, 
                sort_order: Optional[str] = "asc", filter_brand: Optional[str] = None, 
                filter_price_min: Optional[int] = None, filter_price_max: Optional[int] = None, 
                search: Optional[str] = None) -> List[EnergyDrink]:
        query = self.db.query(EnergyDrink)

        # Применение фильтров
        if filter_brand:
            query = query.filter(EnergyDrink.brand == filter_brand)
        if filter_price_min:
            query = query.filter(EnergyDrink.price >= filter_price_min)
        if filter_price_max:
            query = query.filter(EnergyDrink.price <= filter_price_max)
        if search:
            query = query.filter((EnergyDrink.brand.contains(search)) | (EnergyDrink.name.contains(search)))

        # Применение сортировки
        if sort_by:
            column = getattr(EnergyDrink, sort_by, None)
            if column is not None:
                if sort_order.lower() == "desc":
                    query = query.order_by(column.desc())
                else:
                    query = query.order_by(column.asc())

        # Пагинация
        return query.offset(skip).limit(limit).all()

    def get_by_id(self, drink_id: int) -> Optional[EnergyDrink]:
        return self.db.query(EnergyDrink).filter(EnergyDrink.id == drink_id).first()

    def create(self, drink_data: EnergyDrinkCreate) -> EnergyDrink:
        db_drink = EnergyDrink(**drink_data.dict())
        self.db.add(db_drink)
        self.db.commit()
        self.db.refresh(db_drink)
        return db_drink

    def update(self, drink_id: int, drink_data: EnergyDrinkUpdate) -> Optional[EnergyDrink]:
        db_drink = self.get_by_id(drink_id)
        if db_drink is None:
            return None
        for key, value in drink_data.dict(exclude_unset=True).items():
            setattr(db_drink, key, value)
        self.db.commit()
        self.db.refresh(db_drink)
        return db_drink

    def delete(self, drink_id: int) -> bool:
        db_drink = self.get_by_id(drink_id)
        if db_drink is None:
            return False
        self.db.delete(db_drink)
        self.db.commit()
        return True
    
class EnergyDrinkController:
    def __init__(self, repository: EnergyDrinkRepository):
        self.repository = repository

    def list_drinks(self, skip: int, limit: int, sort_by: Optional[str], sort_order: Optional[str], 
                    filter_brand: Optional[str], filter_price_min: Optional[int], 
                    filter_price_max: Optional[int], search: Optional[str]) -> List[EnergyDrinkResponse]:
        drinks = self.repository.get_all(skip, limit, sort_by, sort_order, filter_brand, filter_price_min, filter_price_max, search)
        return [EnergyDrinkResponse.from_orm(drink) for drink in drinks]

    def get_drink(self, drink_id: int) -> EnergyDrinkResponse:
        drink = self.repository.get_by_id(drink_id)
        if drink is None:
            raise HTTPException(status_code=404, detail="Energy drink not found")
        return EnergyDrinkResponse.from_orm(drink)

    def create_drink(self, drink_data: EnergyDrinkCreate) -> EnergyDrinkResponse:
        drink = self.repository.create(drink_data)
        return EnergyDrinkResponse.from_orm(drink)

    def update_drink(self, drink_id: int, drink_data: EnergyDrinkUpdate) -> EnergyDrinkResponse:
        drink = self.repository.update(drink_id, drink_data)
        if drink is None:
            raise HTTPException(status_code=404, detail="Energy drink not found")
        return EnergyDrinkResponse.from_orm(drink)

    def delete_drink(self, drink_id: int) -> None:
        if not self.repository.delete(drink_id):
            raise HTTPException(status_code=404, detail="Energy drink not found")

# Зависимость для получения сессии базы данных
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# Зависимость для получения репозитория и контроллера
def get_repository(db: Session = Depends(get_db)) -> EnergyDrinkRepository:
    return EnergyDrinkRepository(db)

def get_controller(repository: EnergyDrinkRepository = Depends(get_repository)) -> EnergyDrinkController:
    return EnergyDrinkController(repository)

app = FastAPI()

@app.get("/energy-drinks/", response_model=List[EnergyDrinkResponse])
def read_drinks(
    skip: int = 0,
    limit: int = 10,
    sort_by: Optional[str] = Query(None, description="Сортировка по полю (например, brand, price)"),
    sort_order: Optional[str] = Query("asc", description="Порядок сортировки (asc/desc)"),
    filter_brand: Optional[str] = Query(None, description="Фильтр по бренду"),
    filter_price_min: Optional[int] = Query(None, description="Минимальная цена"),
    filter_price_max: Optional[int] = Query(None, description="Максимальная цена"),
    search: Optional[str] = Query(None, description="Поиск по бренду или названию"),
    controller: EnergyDrinkController = Depends(get_controller)
):
    return controller.list_drinks(skip, limit, sort_by, sort_order, filter_brand, filter_price_min, filter_price_max, search)

@app.get("/energy-drinks/{drink_id}", response_model=EnergyDrinkResponse)
def read_drink(drink_id: int, controller: EnergyDrinkController = Depends(get_controller)):
    return controller.get_drink(drink_id)

@app.post("/energy-drinks/", response_model=EnergyDrinkResponse)
def create_drink(drink: EnergyDrinkCreate, controller: EnergyDrinkController = Depends(get_controller)):
    return controller.create_drink(drink)

@app.put("/energy-drinks/{drink_id}", response_model=EnergyDrinkResponse)
def update_drink(drink_id: int, drink: EnergyDrinkUpdate, controller: EnergyDrinkController = Depends(get_controller)):
    return controller.update_drink(drink_id, drink)

@app.delete("/energy-drinks/{drink_id}", status_code=204)
def delete_drink(drink_id: int, controller: EnergyDrinkController = Depends(get_controller)):
    controller.delete_drink(drink_id)