type ProgressBarProps = {
  percentage: number;
};

export const ProgressBar = ({percentage}: ProgressBarProps) => {
  return (
    <div className="overflow-hidden h-2 bg-gray-100 rounded-full">
      <div className="h-full bg-blue-600 rounded-full" style={{width: `${percentage}%`}} />
    </div>
  );
};
