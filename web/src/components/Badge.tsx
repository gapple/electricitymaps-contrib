export type PillType = 'default' | 'warning' | 'success';

type BadgeProps = {
  pillText: string;
  type?: PillType;
  icon?: string;
};

export default function Badge({ pillText, type, icon }: BadgeProps) {
  let classes = '';

  switch (type) {
    case 'warning': {
      classes =
        'bg-warning/10 dark:bg-warning-dark/10 text-warning dark:text-warning-dark';
      break;
    }
    case 'success': {
      classes =
        'bg-success/10 dark:bg-success-dark/10 text-success dark:text-success-dark';
      break;
    }
    default: {
      classes = 'bg-neutral-200 dark:bg-gray-700 text-black dark:text-white';
    }
  }

  return (
    <span
      className={`ml-2 flex h-[22px] flex-row items-center gap-1 whitespace-nowrap rounded-full px-2 py-1 text-xs font-semibold ${classes}`}
      data-test-id="badge"
    >
      {icon != undefined && <div className={`${icon}`} />}
      {pillText}
    </span>
  );
}
