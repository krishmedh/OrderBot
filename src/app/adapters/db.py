from sqlalchemy import Column, Float, Integer, String, create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

Base = declarative_base()


class ProductTable(Base):
    __tablename__ = "products"
    sku = Column(String, primary_key=True)
    name = Column(String, nullable=False)
    quantity_available = Column(Integer, nullable=False)
    price = Column(Float, nullable=False)


class OrderTable(Base):
    __tablename__ = "orders"
    order_id = Column(String, primary_key=True)
    customer_phone = Column(String, nullable=False)
    items_json = Column(String, nullable=False)
    total_amount = Column(Float, nullable=False)
    status = Column(String, nullable=False)
    store_id = Column(String, nullable=True)


def create_session_factory(database_url: str):
    engine = create_engine(database_url, future=True)
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
