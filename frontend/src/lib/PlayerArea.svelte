<script lang="ts">
  import { DISCARD, HAND } from "./enums";
  import Hand from "./Hand.svelte";
  import OwnPlacedBoard from "./OwnPlacedBoard.svelte";
  import type { PlayerT } from "./types";
  import WithDiscardOnLeft from "./WithDiscardOnLeft.svelte";

  let {player_data}: {player_data: PlayerT} = $props();
</script>

<div id="our-area">
  <Hand cards={Object.values(player_data.areas[HAND])}/>
  <WithDiscardOnLeft discard_area={player_data.areas[DISCARD]}>
    <OwnPlacedBoard player_data={player_data}/>
  </WithDiscardOnLeft>
</div>

<style>
#our-area {
  display: flex;
  flex-direction: column;
  align-items: stretch;
  min-width: fit-content;
}
</style>
