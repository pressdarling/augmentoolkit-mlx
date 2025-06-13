import plotly.graph_objects as go
import plotly.express as px
import pandas as pd

# Data for the chart
data = {
    "method": ["GGUF Q4_K_M", "GGUF Q8_0", "GGUF F16", "MLX 4-bit", "MLX 8-bit", "LoRA Tune", "Full Tune", "Augment Gen"],
    "max_model_size": [32, 20, 12, 34, 22, 30, 8, 13],
    "quantization": ["4-bit", "8-bit", "16-bit", "4-bit", "8-bit", "Mixed", "16-bit", "Mixed"]
}

df = pd.DataFrame(data)

# Define colors for different quantization levels
color_map = {
    "4-bit": "#1FB8CD",
    "8-bit": "#FFC185", 
    "16-bit": "#ECEBD5",
    "Mixed": "#5D878F"
}

# Create the bar chart
fig = go.Figure()

for quant in ["4-bit", "8-bit", "16-bit", "Mixed"]:
    df_filtered = df[df["quantization"] == quant]
    if not df_filtered.empty:
        fig.add_trace(go.Bar(
            x=df_filtered["method"],
            y=df_filtered["max_model_size"],
            name=quant,
            marker_color=color_map[quant],
            cliponaxis=False
        ))

# Update layout
fig.update_layout(
    title="Mac Studio M1 Ultra Model Compatibility",
    xaxis_title="Method",
    yaxis_title="Max Size (B)",
    barmode='group',
    legend=dict(orientation='h', yanchor='bottom', y=1.05, xanchor='center', x=0.5)
)

# Update y-axis to show values in billions
fig.update_yaxes(ticksuffix="B")

# Save the chart
fig.write_image("mac_studio_model_compatibility.png")