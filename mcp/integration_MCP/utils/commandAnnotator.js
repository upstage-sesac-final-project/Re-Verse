/**
 * Annotates an event command with a human-readable description.
 * @param {import('../types/index.js').EventCommand} cmd - Event command to annotate
 * @returns {import('../types/index.js').EventCommand} Annotated command with _description property
 */
export const annotateCommand = (cmd) => {
    let description = "";
    switch (cmd.code) {
        case 101: description = `Show Text: Face=${cmd.parameters[0]}(${cmd.parameters[1]})`; break;
        case 401: description = `Text: ${cmd.parameters[0]}`; break;
        case 102: description = `Show Choices: ${JSON.stringify(cmd.parameters[0])}`; break;
        case 402: description = `When: [${cmd.parameters[1]}]`; break;
        case 403: description = `When Cancel`; break;
        case 121: description = `Control Switches: ${cmd.parameters[0]}-${cmd.parameters[1]} = ${cmd.parameters[2] === 0 ? 'ON' : 'OFF'}`; break;
        case 122: description = `Control Variables: ${cmd.parameters[0]}-${cmd.parameters[1]} = ${cmd.parameters[3]}`; break;
        case 231: description = `Show Picture: #${cmd.parameters[0]} ${cmd.parameters[1]}`; break;
        case 201: description = `Transfer Player: Map ${cmd.parameters[1]} (${cmd.parameters[2]},${cmd.parameters[3]})`; break;
        case 112: description = `Loop`; break;
        case 413: description = `Repeat Above`; break;
        case 113: description = `Break Loop`; break;
        case 111: description = `Conditional Branch: Code=${cmd.parameters[0]} A=${cmd.parameters[1]} Op=${cmd.parameters[2]} B=${cmd.parameters[3]}`; break;
        case 411: description = `Else`; break;
        case 412: description = `Branch End`; break;
    }
    return {
        ...cmd,
        _description: description || undefined
    };
};
