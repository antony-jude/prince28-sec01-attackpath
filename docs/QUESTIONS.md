# ATT&CK Mapping Evaluation Questions

These are ten seed prompts for the future evaluation set. They are not scored examples until a reviewer records the expected technique IDs against a pinned ATT&CK release. Keep the incident wording separate from the answer key to avoid leaking labels into evaluation prompts.

| # | Evaluation prompt |
| --- | --- |
| 1 | An employee opens an unexpected document attachment. The document launches a script interpreter, which then contacts an unfamiliar external host. Which ATT&CK techniques best describe the observed activity? |
| 2 | An endpoint runs an encoded command through PowerShell, retrieves a file from an external server, and executes it. Which techniques should an analyst investigate? |
| 3 | A suspicious executable is configured to run automatically each time a workstation starts. Which persistence behavior does this suggest? |
| 4 | An unfamiliar process creates a new scheduled task shortly after an untrusted program runs. Which techniques may explain the persistence and execution? |
| 5 | A public-facing web server starts running commands through a newly discovered server-side script. Which techniques fit the evidence? |
| 6 | A log contains only a process ID (`1234`) and timestamp. It omits the hostname, executable, user, command line, and surrounding events. Which ATT&CK technique was used? |
| 7 | A cloud audit log shows a principal listing resources and creating a new access key outside its normal workflow. Which techniques should be considered? |
| 8 | Several files on a workstation and a mapped share are renamed and become unreadable; a ransom note appears. Which techniques describe the observed impact? |
| 9 | An external host initiates repeated remote desktop connections to several workstations, followed by interactive logons. Which techniques may apply? |
| 10 | A host makes regular DNS requests to a rare domain, with unusually long subdomain labels and a repeated pattern of encoded-looking data. Which techniques should be evaluated? |

## Labeling checklist

- Record all applicable technique and sub-technique IDs for each prompt.
- Record the ATT&CK domain and release used for each label.
- Have a reviewer verify labels against the cited ATT&CK pages.
- Keep ambiguous or insufficiently evidenced cases out of the scored set.
- Expand the reviewed set to at least 50 incidents before reporting the 80% top-3 target.
