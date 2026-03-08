from sqlalchemy import Column, Integer, String, Text, ForeignKey, JSON
from sqlalchemy.orm import relationship
from database import Base

class UserProfile(Base):
    __tablename__ = "user_profiles"

    id = Column(Integer, primary_key=True, index=True)
    phone_number = Column(String, unique=True, index=True, nullable=True) # Optional form of identity
    name = Column(String, nullable=True)
    age = Column(Integer, nullable=True)
    income = Column(Integer, nullable=True)
    state = Column(String, nullable=True)
    occupations = Column(JSON, nullable=True) # List of occupations like "farmer", "student"
    
    sessions = relationship("SessionHistory", back_populates="user")


class Scheme(Base):
    __tablename__ = "schemes"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True)
    description = Column(Text)
    eligibility_criteria = Column(Text)
    benefits = Column(Text)
    state = Column(String, index=True) # "Central" or specific state
    tags = Column(JSON) # e.g. ["agriculture", "women", "health"]

class SessionHistory(Base):
    __tablename__ = "session_history"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("user_profiles.id"), nullable=True)
    session_id = Column(String, unique=True, index=True) # UUID for the conversation
    context = Column(JSON) # Store entire conversation history here for simplicity

    user = relationship("UserProfile", back_populates="sessions")

class Turn(Base):
    __tablename__ = "turns"

    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(String, ForeignKey("session_history.session_id"))
    user_message = Column(Text)
    bot_response = Column(Text)
    action_items = Column(JSON, nullable=True)
    cited_schemes = Column(JSON, nullable=True)
