# import requests

# url = "http://localhost:11434/api/generate"

# payload = {
#     "model": "llama3:latest",  # or "llama3:latest"
#     "prompt": "Summarize the following lecture content in bullet points:\n\n"
#               "Normalization is a database design technique that reduces data redundancy "
#               "and improves data integrity. It organizes data using normal forms such as "
#               "1NF, 2NF, and 3NF.",
#     "stream": False
# }

# response = requests.post(url, json=payload)

# print(response.status_code)
# print(response.json())   # 👈 PRINT EVERYTHING

from app.ca_guidance.tools.rag_tool import summarize_lecture_materials

result = summarize_lecture_materials.run("Normalization")
print(result)
