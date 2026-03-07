import { Doughnut } from 'react-chartjs-2';
import {
  Chart as ChartJS,
  ArcElement,
  Tooltip,
  Legend,
} from 'chart.js';

ChartJS.register(ArcElement, Tooltip, Legend);

const PALETTE = [
  '#8b5cf6', '#a78bfa', '#c4b5fd',
  '#7c3aed', '#6d28d9', '#5b21b6',
  '#ddd6fe', '#ede9fe',
];

export default function TopicDoughnutChart({ topics = {} }) {
  const labels = Object.keys(topics);
  const values = Object.values(topics);

  const data = {
    labels,
    datasets: [
      {
        data: values,
        backgroundColor: labels.map((_, i) => PALETTE[i % PALETTE.length]),
        borderWidth: 0,
        hoverOffset: 8,
      },
    ],
  };

  const options = {
    responsive: true,
    maintainAspectRatio: false,
    cutout: '60%',
    plugins: {
      legend: {
        position: 'bottom',
        labels: {
          color: '#9a8cb0',
          padding: 14,
          usePointStyle: true,
          pointStyleWidth: 10,
          font: { size: 12 },
        },
      },
      tooltip: {
        backgroundColor: '#1a1425',
        borderColor: '#2d2540',
        borderWidth: 1,
        titleColor: '#e8e0f0',
        bodyColor: '#e8e0f0',
      },
    },
  };

  return (
    <div style={{ height: 280 }}>
      <Doughnut data={data} options={options} />
    </div>
  );
}
