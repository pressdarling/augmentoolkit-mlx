import plotly.graph_objects as go
import json

# Data provided
data = {
  "methods": [
    {
      "name": "RAG",
      "cost": 6,
      "speed": 7,
      "knowledge_persistence": 3,
      "hardware_requirements": 4,
      "accuracy": 7,
      "maintenance_overhead": 7
    },
    {
      "name": "Full Fine-tuning",
      "cost": 2,
      "speed": 4,
      "knowledge_persistence": 10,
      "hardware_requirements": 2,
      "accuracy": 9,
      "maintenance_overhead": 3
    },
    {
      "name": "LoRA/QLoRA",
      "cost": 7,
      "speed": 7,
      "knowledge_persistence": 8,
      "hardware_requirements": 7,
      "accuracy": 8,
      "maintenance_overhead": 4
    },
    {
      "name": "Augmentoolkit",
      "cost": 8,
      "speed": 6,
      "knowledge_persistence": 9,
      "hardware_requirements": 6,
      "accuracy": 8,
      "maintenance_overhead": 5
    },
    {
      "name": "In-Context Learning",
      "cost": 9,
      "speed": 9,
      "knowledge_persistence": 2,
      "hardware_requirements": 9,
      "accuracy": 6,
      "maintenance_overhead": 9
    },
    {
      "name": "Model Editing",
      "cost": 8,
      "speed": 8,
      "knowledge_persistence": 6,
      "hardware_requirements": 8,
      "accuracy": 5,
      "maintenance_overhead": 6
    }
  ]
}

# Define dimensions with abbreviated names (max 15 chars)
dimensions = [
    'Cost', 'Speed', 'Know Persist', 'Hardware Req', 'Accuracy', 'Maintenance'
]

# Brand colors for each method
colors = ['#1FB8CD', '#FFC185', '#ECEBD5', '#5D878F', '#D2BA4C', '#B4413C']

# Create the radar chart
fig = go.Figure()

# Add each method as a trace
for i, method in enumerate(data['methods']):
    # Get values for each dimension
    values = [
        method['cost'],
        method['speed'], 
        method['knowledge_persistence'],
        method['hardware_requirements'],
        method['accuracy'],
        method['maintenance_overhead']
    ]
    
    # Abbreviate method names if needed (max 15 chars)
    method_name = method['name']
    if method_name == "Full Fine-tuning":
        method_name = "Full Fine-tune"
    elif method_name == "In-Context Learning":
        method_name = "In-Context Lrn"
    
    # Add the trace
    fig.add_trace(go.Scatterpolar(
        r=values + [values[0]],  # Close the polygon
        theta=dimensions + [dimensions[0]],  # Close the polygon
        fill='toself',
        name=method_name,
        line_color=colors[i],
        fillcolor=colors[i],
        opacity=0.6,
        cliponaxis=False
    ))

# Update layout
fig.update_layout(
    title='LLM Knowledge Update Methods',
    polar=dict(
        radialaxis=dict(
            visible=True,
            range=[0, 10],
            showticklabels=True,
            tickmode='linear',
            tick0=0,
            dtick=2
        )
    ),
    showlegend=True
)

# Save the chart
fig.write_image('llm_comparison_radar.png')