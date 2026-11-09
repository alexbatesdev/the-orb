from __future__ import annotations

import discord
from discord.ext import commands

from wisest_wizard.i18n import translate


class WizardHelpCommand(commands.DefaultHelpCommand):
    def __init__(self) -> None:
        super().__init__(
            arguments_heading=translate("help.arguments_heading"),
            commands_heading=translate("help.commands_heading"),
            default_argument_description=translate("help.argument_no_description"),
            no_category=translate("help.no_category"),
            command_attrs={"help": translate("help.command")},
        )

    def get_ending_note(self) -> str:
        return translate(
            "help.ending_note",
            prefix=self.context.clean_prefix,
            command=self.invoked_with,
        )

    def command_not_found(self, string: str, /) -> str:
        return translate("help.command_not_found", name=string)

    async def command_callback(
        self, ctx: commands.Context, /, *, command: str | None = None
    ) -> None:
        if command is not None and ctx.bot.get_cog(command) is None:
            resolved = ctx.bot.all_commands.get(" ".join(command.split()))
            if resolved is not None:
                await self.prepare_help_command(ctx, command)
                if isinstance(resolved, commands.Group):
                    await self.send_group_help(resolved)
                else:
                    await self.send_command_help(resolved)
                return
        await super().command_callback(ctx, command=command)

    def subcommand_not_found(
        self, command: commands.Command, string: str, /
    ) -> str:
        prefix = command.qualified_name.lower() + " "
        if (
            isinstance(command, commands.Group) and command.all_commands
        ) or any(name.lower().startswith(prefix) for name in self.context.bot.all_commands):
            return translate(
                "help.subcommand_not_found", command=command.qualified_name, name=string
            )
        return translate("help.no_subcommands", command=command.qualified_name)

    def add_command_arguments(self, command: commands.Command, /) -> None:
        arguments = command.clean_params.values()
        if not arguments:
            return
        self.paginator.add_line(self.arguments_heading)
        max_size = self.get_max_size(arguments)
        for argument in arguments:
            name = argument.displayed_name or argument.name
            width = max_size - (discord.utils._string_width(name) - len(name))
            entry = (
                f'{self.indent * " "}{name:<{width}} '
                f"{argument.description or self.default_argument_description}"
            )
            entry = self.shorten_text(entry)
            if argument.displayed_default is not None:
                entry += translate("help.argument_default", value=argument.displayed_default)
            self.paginator.add_line(entry)
