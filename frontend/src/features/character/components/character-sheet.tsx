import { useGameStore } from "../../../shared/stores/game-store";
import { getHP, abilityModNum } from "../../../shared/utils/dnd";

export default function CharacterSheet() {
  const campaign = useGameStore((s) => s.campaign);
  if (!campaign) return null;

  const char = campaign.character_data;
  if (!char || !char.name) return <p className="text-parchment-500">No character data</p>;

  const hp = getHP(char);

  return (
    <div>
      <h3 className="mb-4 font-display text-xl text-gold-400">{char.name}</h3>

      {/* HP Bar */}
      <div className="mb-4">
        <div className="mb-1 flex justify-between text-sm">
          <span className="text-parchment-300">HP</span>
          <span className="text-parchment-400">
            {hp.current}/{hp.max}
          </span>
        </div>
        <div className="h-3 overflow-hidden rounded-full bg-parchment-800">
          <div
            className="h-full rounded-full bg-red-600 transition-all"
            style={{ width: `${hp.max > 0 ? (hp.current / hp.max) * 100 : 0}%` }}
          />
        </div>
      </div>

      <div className="mb-4 flex justify-between text-sm">
        <span className="text-parchment-300">Level {char.level}</span>
        <span className="text-parchment-500">{char.xp} XP</span>
      </div>

      <div className="mb-4 flex gap-4 text-sm">
        <span>
          <span className="text-parchment-400">AC: </span>
          <span className="font-bold text-parchment-200">{char.ac}</span>
        </span>
        <span>
          <span className="text-parchment-400">Gold: </span>
          <span className="font-bold text-gold-400">{char.gold}</span>
        </span>
      </div>

      {/* Abilities */}
      <h4 className="mb-2 text-sm font-semibold uppercase tracking-wider text-parchment-500">
        Abilities
      </h4>
      <div className="mb-4 grid grid-cols-2 gap-2">
        {Object.entries(char.abilities || {}).map(([ability, score]) => (
          <div
            key={ability}
            className="rounded border border-parchment-700/20 px-2 py-1 text-center"
          >
            <div className="text-xs uppercase text-parchment-500">{ability.slice(0, 3)}</div>
            <div className="font-bold text-parchment-200">{score as number}</div>
            <div className="text-xs text-parchment-500">
              {abilityModNum(score as number) >= 0 ? "+" : ""}
              {abilityModNum(score as number)}
            </div>
          </div>
        ))}
      </div>

      {/* Skills */}
      {char.skills && Object.keys(char.skills).length > 0 && (
        <>
          <h4 className="mb-2 text-sm font-semibold uppercase tracking-wider text-parchment-500">
            Skills
          </h4>
          <div className="mb-4 space-y-1">
            {Object.entries(char.skills).map(([skill, data]) => (
              <div key={skill} className="flex justify-between text-sm">
                <span className="capitalize text-parchment-300">{skill}</span>
                <span className="text-parchment-500">Lv {data.level}</span>
              </div>
            ))}
          </div>
        </>
      )}

      {/* Equipped */}
      {char.equipped && Object.keys(char.equipped).length > 0 && (
        <>
          <h4 className="mb-2 text-sm font-semibold uppercase tracking-wider text-parchment-500">
            Equipped
          </h4>
          <div className="mb-4 space-y-1">
            {Object.entries(char.equipped).map(
              ([slot, item]) =>
                item && (
                  <div key={slot} className="flex justify-between text-sm">
                    <span className="capitalize text-parchment-400">{slot}</span>
                    <span className="text-parchment-200">{item}</span>
                  </div>
                ),
            )}
          </div>
        </>
      )}

      {/* Inventory */}
      <h4 className="mb-2 text-sm font-semibold uppercase tracking-wider text-parchment-500">
        Inventory
      </h4>
      <div className="mb-4 space-y-1">
        {(char.inventory || []).map((item, i) => (
          <div key={i} className="text-sm text-parchment-300">
            {item.name}{" "}
            {item.quantity > 1 && <span className="text-parchment-500">x{item.quantity}</span>}
          </div>
        ))}
        {(!char.inventory || char.inventory.length === 0) && (
          <p className="text-xs text-parchment-600">Empty</p>
        )}
      </div>

      {/* Reputation */}
      {char.reputation && Object.keys(char.reputation).length > 0 && (
        <>
          <h4 className="mb-2 text-sm font-semibold uppercase tracking-wider text-parchment-500">
            Reputation
          </h4>
          <div className="mb-4 space-y-1">
            {Object.entries(char.reputation).map(([faction, score]) => (
              <div key={faction} className="flex justify-between text-sm">
                <span className="text-parchment-300">{faction}</span>
                <span className={(score as number) >= 0 ? "text-green-400" : "text-red-400"}>
                  {(score as number) >= 0 ? "+" : ""}
                  {score as number}
                </span>
              </div>
            ))}
          </div>
        </>
      )}

      {/* Background */}
      {char.background && (
        <div className="mt-4 border-t border-parchment-700/20 pt-3">
          <h4 className="mb-1 text-sm font-semibold uppercase tracking-wider text-parchment-500">
            Background
          </h4>
          <p className="text-sm text-parchment-400">{char.background}</p>
        </div>
      )}
    </div>
  );
}
