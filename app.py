from fastapi import FastAPI, HTTPException, Depends, Query
from pydantic import BaseModel
from sqlalchemy import create_engine, Column, Integer, String
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session
from typing import List, Optional

# Настройка базы данных
DATABASE_URL = "sqlite:///./sneakers.db"

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# Модель базы данных
class Sneaker(Base):
    __tablename__ = "sneakers"
    id = Column(Integer, primary_key=True, index=True)
    brand = Column(String, index=True)
    model = Column(String)
    price = Column(Integer)

Base.metadata.create_all(bind=engine)

# Модели Pydantic для валидации
class SneakerCreate(BaseModel):
    brand: str
    model: str
    price: int

class SneakerUpdate(BaseModel):
    brand: Optional[str] = None
    model: Optional[str] = None
    price: Optional[int] = None

class SneakerResponse(BaseModel):
    id: int
    brand: str
    model: str
    price: int

    class Config:
        from_attributes = True

class SneakerRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_all(self, skip: int = 0, limit: int = 10, sort_by: Optional[str] = None, 
                sort_order: Optional[str] = "asc", filter_brand: Optional[str] = None, 
                filter_price_min: Optional[int] = None, filter_price_max: Optional[int] = None, 
                search: Optional[str] = None) -> List[Sneaker]:
        query = self.db.query(Sneaker)

        # Применение фильтров
        if filter_brand:
            query = query.filter(Sneaker.brand == filter_brand)
        if filter_price_min:
            query = query.filter(Sneaker.price >= filter_price_min)
        if filter_price_max:
            query = query.filter(Sneaker.price <= filter_price_max)
        if search:
            query = query.filter((Sneaker.brand.contains(search)) | (Sneaker.model.contains(search)))

        # Применение сортировки
        if sort_by:
            column = getattr(Sneaker, sort_by, None)
            if column is not None:
                if sort_order.lower() == "desc":
                    query = query.order_by(column.desc())
                else:
                    query = query.order_by(column.asc())

        # Пагинация
        return query.offset(skip).limit(limit).all()

    def get_by_id(self, sneaker_id: int) -> Optional[Sneaker]:
        return self.db.query(Sneaker).filter(Sneaker.id == sneaker_id).first()

    def create(self, sneaker_data: SneakerCreate) -> Sneaker:
        db_sneaker = Sneaker(**sneaker_data.dict())
        self.db.add(db_sneaker)
        self.db.commit()
        self.db.refresh(db_sneaker)
        return db_sneaker

    def update(self, sneaker_id: int, sneaker_data: SneakerUpdate) -> Optional[Sneaker]:
        db_sneaker = self.get_by_id(sneaker_id)
        if db_sneaker is None:
            return None
        for key, value in sneaker_data.dict(exclude_unset=True).items():
            setattr(db_sneaker, key, value)
        self.db.commit()
        self.db.refresh(db_sneaker)
        return db_sneaker

    def delete(self, sneaker_id: int) -> bool:
        db_sneaker = self.get_by_id(sneaker_id)
        if db_sneaker is None:
            return False
        self.db.delete(db_sneaker)
        self.db.commit()
        return True

class SneakerController:
    def __init__(self, repository: SneakerRepository):
        self.repository = repository
    def list_sneakers(self, skip: int, limit: int, sort_by: Optional[str], sort_order: Optional[str], 
                      filter_brand: Optional[str], filter_price_min: Optional[int], 
                      filter_price_max: Optional[int], search: Optional[str]) -> List[SneakerResponse]:
        sneakers = self.repository.get_all(skip, limit, sort_by, sort_order, filter_brand, filter_price_min, filter_price_max, search)
        return [SneakerResponse.from_orm(sneaker) for sneaker in sneakers]
    def get_sneaker(self, sneaker_id: int) -> SneakerResponse:
        sneaker = self.repository.get_by_id(sneaker_id)
        if sneaker is None:
            raise HTTPException(status_code=404, detail="Sneaker not found")
        return SneakerResponse.from_orm(sneaker)

    def create_sneaker(self, sneaker_data: SneakerCreate) -> SneakerResponse:
        sneaker = self.repository.create(sneaker_data)
        return SneakerResponse.from_orm(sneaker)

    def update_sneaker(self, sneaker_id: int, sneaker_data: SneakerUpdate) -> SneakerResponse:
        sneaker = self.repository.update(sneaker_id, sneaker_data)
        if sneaker is None:
            raise HTTPException(status_code=404, detail="Sneaker not found")
        return SneakerResponse.from_orm(sneaker)

    def delete_sneaker(self, sneaker_id: int) -> None:
        if not self.repository.delete(sneaker_id):
            raise HTTPException(status_code=404, detail="Sneaker not found")

# Зависимость для получения сессии базы данных
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# Зависимость для получения репозитория и контроллера
def get_repository(db: Session = Depends(get_db)) -> SneakerRepository:
    return SneakerRepository(db)

def get_controller(repository: SneakerRepository = Depends(get_repository)) -> SneakerController:
    return SneakerController(repository)

app = FastAPI()

@app.get("/sneakers/", response_model=List[SneakerResponse])
def read_sneakers(
    skip: int = 0,
    limit: int = 10,
    sort_by: Optional[str] = Query(None, description="Сортировка по полю (например, brand, price)"),
    sort_order: Optional[str] = Query("asc", description="Порядок сортировки (asc/desc)"),
    filter_brand: Optional[str] = Query(None, description="Фильтр по бренду"),
    filter_price_min: Optional[int] = Query(None, description="Минимальная цена"),
    filter_price_max: Optional[int] = Query(None, description="Максимальная цена"),
    search: Optional[str] = Query(None, description="Поиск по бренду или модели"),
    controller: SneakerController = Depends(get_controller)
):
    return controller.list_sneakers(skip, limit, sort_by, sort_order, filter_brand, filter_price_min, filter_price_max, search)

@app.get("/sneakers/{sneaker_id}", response_model=SneakerResponse)
def read_sneaker(sneaker_id: int, controller: SneakerController = Depends(get_controller)):
    return controller.get_sneaker(sneaker_id)

@app.post("/sneakers/", response_model=SneakerResponse)
def create_sneaker(sneaker: SneakerCreate, controller: SneakerController = Depends(get_controller)):
    return controller.create_sneaker(sneaker)

@app.put("/sneakers/{sneaker_id}", response_model=SneakerResponse)
def update_sneaker(sneaker_id: int, sneaker: SneakerUpdate, controller: SneakerController = Depends(get_controller)):
    return controller.update_sneaker(sneaker_id, sneaker)

@app.delete("/sneakers/{sneaker_id}", status_code=204)
def delete_sneaker(sneaker_id: int, controller: SneakerController = Depends(get_controller)):
    controller.delete_sneaker(sneaker_id)