import { useId, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { getCampaignLanguages } from "../../../shared/api/client";

interface Props {
  value: string;
  onChange: (code: string) => void;
  disabled?: boolean;
}

export default function LanguageSelect({ value, onChange, disabled = false }: Props) {
  const { t } = useTranslation();
  const id = useId();
  const [search, setSearch] = useState("");
  const { data, isPending, isError, refetch } = useQuery({
    queryKey: ["campaign-languages"],
    queryFn: () => getCampaignLanguages().then((response) => response.data),
    staleTime: Infinity,
  });
  const query = search.trim().toLowerCase();
  const options = data?.filter(
    (entry) =>
      entry.code === value || `${entry.display_name} ${entry.code}`.toLowerCase().includes(query),
  );
  const controlClass =
    "w-full rounded-lg px-3 py-2 font-display text-sm focus:outline-none focus:ring-1 focus:ring-accent";
  const controlStyle = {
    color: "var(--ink-primary)",
    background: "var(--parchment-aged)",
    border: "1px solid var(--line-strong)",
  };

  return (
    <div className="space-y-2">
      <label
        htmlFor={id}
        className="block font-display text-xs"
        style={{ color: "var(--ink-secondary)" }}
      >
        {t("campaign.language")}
      </label>
      <input
        type="search"
        aria-label={t("campaign.language_search")}
        placeholder={t("campaign.language_search")}
        value={search}
        onChange={(event) => setSearch(event.target.value)}
        disabled={disabled || isPending || isError}
        className={controlClass}
        style={controlStyle}
      />
      <select
        id={id}
        value={value}
        onChange={(event) => onChange(event.target.value)}
        disabled={disabled || isPending || isError}
        className={controlClass}
        style={controlStyle}
        aria-describedby={`${id}-hint`}
      >
        {!data && <option value={value}>{value}</option>}
        {options?.map((entry) => (
          <option key={entry.code} value={entry.code}>
            {entry.display_name} ({entry.code})
          </option>
        ))}
      </select>
      <p id={`${id}-hint`} className="font-display text-xs" style={{ color: "var(--ink-faded)" }}>
        {t("campaign.language_hint")}
      </p>
      {isError && (
        <div role="alert" className="font-display text-xs" style={{ color: "var(--blood)" }}>
          {t("campaign.language_load_error")}{" "}
          <button onClick={() => void refetch()}>{t("campaign.language_retry")}</button>
        </div>
      )}
    </div>
  );
}
