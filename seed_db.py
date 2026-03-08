import os
from database import engine, Base, SessionLocal
from models import Scheme
from sentence_transformers import SentenceTransformer
import chromadb

# Initialize the embedder
print("Loading sentence-transformers model...")
embedder = SentenceTransformer('all-MiniLM-L6-v2')

# Setup ChromaDB client
print("Setting up local ChromaDB...")
chroma_client = chromadb.PersistentClient(path="./chroma_db")
collection = chroma_client.get_or_create_collection(name="schemes")

# Define a function to generate a large number of dummy/synthetic Indian Government Schemes
def generate_schemes():
    schemes = [
        {
            "name": "PM-KISAN (Pradhan Mantri Kisan Samman Nidhi)",
            "description": "An initiative by the government of India in which all farmers will get up to ₹6,000 per year as minimum income support.",
            "eligibility_criteria": "Small and marginal farmer families having cultivable landholding up to 2 hectares.",
            "benefits": "₹6,000 per year in three equal installments.",
            "state": "Central",
            "tags": ["agriculture", "financial assistance"]
        },
        {
            "name": "Ayushman Bharat Yojana",
            "description": "A national public health insurance fund of the Government of India that aims to provide free access to health insurance coverage for low income earners in the country.",
            "eligibility_criteria": "Families belonging to poor or vulnerable groups based on SECC database.",
            "benefits": "Health cover of ₹5 lakhs per family per year.",
            "state": "Central",
            "tags": ["health", "insurance"]
        },
        {
            "name": "Pradhan Mantri Awas Yojana (PMAY)",
            "description": "An initiative by Government of India in which affordable housing will be provided to the urban poor with a target of building 20 million affordable houses.",
            "eligibility_criteria": "EWS, LIG, and MIG families. Beneficiary family should not own a pucca house.",
            "benefits": "Credit linked subsidy on home loans.",
            "state": "Central",
            "tags": ["housing", "urban"]
        },
        {
            "name": "Mahatma Gandhi National Rural Employment Guarantee Act (MGNREGA)",
            "description": "An Indian labour law and social security measure that aims to guarantee the 'right to work'.",
            "eligibility_criteria": "Adult members of rural households willing to do unskilled manual work.",
            "benefits": "At least 100 days of wage employment in a financial year.",
            "state": "Central",
            "tags": ["employment", "rural"]
        },
        {
            "name": "Sukanya Samriddhi Yojana",
            "description": "A Government of India backed saving scheme targeted at the parents of girl children. The scheme encourages parents to build a fund for the future education and marriage expenses for their female child.",
            "eligibility_criteria": "Parents or legal guardians can open the account in the name of a girl child below 10 years of age.",
            "benefits": "High interest rate, tax benefits under Section 80C.",
            "state": "Central",
            "tags": ["girl child", "savings", "education"]
        }
    ]

    # Generate additional synthetic schemes to reach 150
    sectors = ["Agriculture", "Education", "Health", "Employment", "Women Empowerment", "Infrastructure", "Technology", "MSME"]
    states = ["Maharashtra", "Uttar Pradesh", "Karnataka", "Gujarat", "Tamil Nadu", "West Bengal", "Bihar", "Rajasthan"]
    
    count = len(schemes)
    while count < 150:
        sector = sectors[count % len(sectors)]
        state = states[(count // len(sectors)) % len(states)]
        
        scheme = {
            "name": f"{state} State {sector} Initiative {count}",
            "description": f"A state-level initiative in {state} aimed at boosting the {sector} sector.",
            "eligibility_criteria": f"Residents of {state} involved in {sector}.",
            "benefits": f"Financial assistance and resources for {sector} development.",
            "state": state,
            "tags": [sector.lower(), state.lower()]
        }
        schemes.append(scheme)
        count += 1
        
    return schemes

def seed_database():
    print("Creating database tables...")
    Base.metadata.create_all(bind=engine)
    
    db = SessionLocal()
    
    try:
        # Check if already seeded
        existing_count = db.query(Scheme).count()
        if existing_count >= 150:
            print("Database already seeded with 150+ schemes. Skipping.")
            return

        print("Generating 150 schemes...")
        schemes_data = generate_schemes()
        
        print("Embedding and storing schemes...")
        for i, data in enumerate(schemes_data):
            # 1. Insert into PostgreSQL
            db_scheme = Scheme(
                name=data["name"],
                description=data["description"],
                eligibility_criteria=data["eligibility_criteria"],
                benefits=data["benefits"],
                state=data["state"],
                tags=data["tags"]
            )
            db.add(db_scheme)
            db.commit()
            db.refresh(db_scheme)
            
            # 2. Embed and insert into ChromaDB
            # Create a rich text representation for better semantic search
            search_text = f"{data['name']}. {data['description']} Eligibility: {data['eligibility_criteria']} Benefits: {data['benefits']}"
            embedding = embedder.encode(search_text).tolist()
            
            collection.add(
                embeddings=[embedding],
                documents=[search_text],
                metadatas=[{
                    "id": str(db_scheme.id),
                    "name": data["name"],
                    "state": data["state"]
                }],
                ids=[str(db_scheme.id)]
            )
            
            if (i+1) % 10 == 0:
                print(f"Processed {i+1}/150 schemes...")
                
        print("Successfully seeded database with 150 schemes.")
        
    except Exception as e:
        print(f"Error seeding database: {e}")
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    seed_database()
