interface Option {
  value: string;
  label: string;
}

interface SelectFieldProps {
  id: string;
  label: string;
  value: string;
  onChange: (value: string) => void;
  options: Option[];
  required?: boolean;
  /** Label for the empty/placeholder option (value ""). */
  placeholder?: string;
}

/** Labeled dropdown. Presentational, controlled via props. */
export function SelectField({
  id,
  label,
  value,
  onChange,
  options,
  required = false,
  placeholder,
}: SelectFieldProps) {
  return (
    <div>
      <label
        htmlFor={id}
        className="mb-1 block text-sm font-medium text-slate-300"
      >
        {label}
        {required && <span className="text-teal-400"> *</span>}
      </label>
      <select
        id={id}
        required={required}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="w-full rounded-xl border border-slate-700 bg-slate-900 px-4 py-3 text-sm text-white focus:border-teal-400 focus:outline-none"
      >
        {placeholder !== undefined && <option value="">{placeholder}</option>}
        {options.map((o) => (
          <option key={o.value} value={o.value}>
            {o.label}
          </option>
        ))}
      </select>
    </div>
  );
}
