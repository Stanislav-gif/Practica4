from fastapi import FastAPI, HTTPException, Depends, Query
from pydantic import BaseModel
from sqlalchemy import create_engine, Column, Integer, String, Float
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session
from typing import List, Optional

# Настройка базы данных
DATABASE_URL = "sqlite:///./vapes.db"

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# Модель базы данных
class Vape(Base):
    __tablename__ = "vapes"
    id = Column(Integer, primary_key=True, index=True)
    brand = Column(String, index=True)
    model = Column(String)              
    price = Column(Float)               
    power_level = Column(Float)         # Уровень мощности (Вт)

Base.metadata.create_all(bind=engine)

# Модели Pydantic для валидации
class VapeCreate(BaseModel):
    brand: str
    model: str
    price: float
    power_level: float

class VapeUpdate(BaseModel):
    brand: Optional[str] = None
    model: Optional[str] = None
    price: Optional[float] = None
    power_level: Optional[float] = None

class VapeResponse(BaseModel):
    id: int
    brand: str
    model: str
    price: float
    power_level: float

    class Config:
        from_attributes = True

class VapeRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_all(self, skip: int = 0, limit: int = 10, sort_by: Optional[str] = None, 
                sort_order: Optional[str] = "asc", filter_brand: Optional[str] = None, 
                filter_price_min: Optional[float] = None, filter_price_max: Optional[float] = None, 
                search: Optional[str] = None) -> List[Vape]:
        query = self.db.query(Vape)

        # Применение фильтров
        if filter_brand:
            query = query.filter(Vape.brand == filter_brand)
        if filter_price_min:
            query = query.filter(Vape.price >= filter_price_min)
        if filter_price_max:
            query = query.filter(Vape.price <= filter_price_max)
        if search:
            query = query.filter((Vape.brand.contains(search)) | (Vape.model.contains(search)))

        # Применение сортировки
        if sort_by:
            column = getattr(Vape, sort_by, None)
            if column is not None:
                if sort_order.lower() == "desc":
                    query = query.order_by(column.desc())
                else:
                    query = query.order_by(column.asc())

        # Пагинация
        return query.offset(skip).limit(limit).all()

    def get_by_id(self, vape_id: int) -> Optional[Vape]:
        return self.db.query(Vape).filter(Vape.id == vape_id).first()

    def create(self, vape_data: VapeCreate) -> Vape:
        db_vape = Vape(**vape_data.dict())
        self.db.add(db_vape)
        self.db.commit()
        self.db.refresh(db_vape)
        return db_vape

    def update(self, vape_id: int, vape_data: VapeUpdate) -> Optional[Vape]:
        db_vape = self.get_by_id(vape_id)
        if db_vape is None:
            return None
        for key, value in vape_data.dict(exclude_unset=True).items():
            setattr(db_vape, key, value)
        self.db.commit()
        self.db.refresh(db_vape)
        return db_vape

    def delete(self, vape_id: int) -> bool:
        db_vape = self.get_by_id(vape_id)
        if db_vape is None:
            return False
        self.db.delete(db_vape)
        self.db.commit()
        return True

class VapeController:
    def __init__(self, repository: VapeRepository):
        self.repository = repository

    def list_vapes(self, skip: int, limit: int, sort_by: Optional[str], sort_order: Optional[str], 
                   filter_brand: Optional[str], filter_price_min: Optional[float], 
                   filter_price_max: Optional[float], search: Optional[str]) -> List[VapeResponse]:
        vapes = self.repository.get_all(skip, limit, sort_by, sort_order, filter_brand, filter_price_min, filter_price_max, search)
        return [VapeResponse.from_orm(vape) for vape in vapes]

    def get_vape(self, vape_id: int) -> VapeResponse:
        vape = self.repository.get_by_id(vape_id)
        if vape is None:
            raise HTTPException(status_code=404, detail="Vape not found")
        return VapeResponse.from_orm(vape)

    def create_vape(self, vape_data: VapeCreate) -> VapeResponse:
        vape = self.repository.create(vape_data)
        return VapeResponse.from_orm(vape)

    def update_vape(self, vape_id: int, vape_data: VapeUpdate) -> VapeResponse:
        vape = self.repository.update(vape_id, vape_data)
        if vape is None:
            raise HTTPException(status_code=404, detail="Vape not found")
        return VapeResponse.from_orm(vape)

    def delete_vape(self, vape_id: int) -> None:
        if not self.repository.delete(vape_id):
            raise HTTPException(status_code=404, detail="Vape not found")

# Зависимость для получения сессии базы данных
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# Зависимость для получения репозитория и контроллера
def get_repository(db: Session = Depends(get_db)) -> VapeRepository:
    return VapeRepository(db)

def get_controller(repository: VapeRepository = Depends(get_repository)) -> VapeController:
    return VapeController(repository)

app = FastAPI()

@app.get("/vapes/", response_model=List[VapeResponse])
def read_vapes(
    skip: int = 0,
    limit: int = 10,
    sort_by: Optional[str] = Query(None, description="Сортировка по полю (например, brand, price)"),
    sort_order: Optional[str] = Query("asc", description="Порядок сортировки (asc/desc)"),
    filter_brand: Optional[str] = Query(None, description="Фильтр по бренду"),
    filter_price_min: Optional[float] = Query(None, description="Минимальная цена"),
    filter_price_max: Optional[float] = Query(None, description="Максимальная цена"),
    search: Optional[str] = Query(None, description="Поиск по бренду или модели"),
    controller: VapeController = Depends(get_controller)
):
    return controller.list_vapes(skip, limit, sort_by, sort_order, filter_brand, filter_price_min, filter_price_max, search)

@app.get("/vapes/{vape_id}", response_model=VapeResponse)
def read_vape(vape_id: int, controller: VapeController = Depends(get_controller)):
    return controller.get_vape(vape_id)

@app.post("/vapes/", response_model=VapeResponse)
def create_vape(vape: VapeCreate, controller: VapeController = Depends(get_controller)):
    return controller.create_vape(vape)

@app.put("/vapes/{vape_id}", response_model=VapeResponse)
def update_vape(vape_id: int, vape: VapeUpdate, controller: VapeController = Depends(get_controller)):
    return controller.update_vape(vape_id, vape)

@app.delete("/vapes/{vape_id}", status_code=204)
def delete_vape(vape_id: int, controller: VapeController = Depends(get_controller)):
    controller.delete_vape(vape_id)