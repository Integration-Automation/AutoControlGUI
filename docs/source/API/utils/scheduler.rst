Scheduler API
----

.. code-block:: python

    def add_blocking_job(
        self, func: Callable, trigger: str = None, args: Union[list, tuple] = None,
        kwargs: dict = None, id: str = None, name: str = None,
        misfire_grace_time: int = undefined, coalesce: bool = undefined, max_instances: int = undefined,
        next_run_time: datetime = undefined, jobstore: str = 'default', executor: str = 'default',
        replace_existing: bool = False, **trigger_args: Any) -> Job:
            """
            Just an apscheduler add job wrapper.
            :param func: callable (or a textual reference to one) to run at the given time
            :param str|apscheduler.triggers.base.BaseTrigger trigger: trigger that determines when
                ``func`` is called
            :param list|tuple args: list of positional arguments to call func with
            :param dict kwargs: dict of keyword arguments to call func with
            :param str|unicode id: explicit identifier for the job (for modifying it later)
            :param str|unicode name: textual description of the job
            :param int misfire_grace_time: seconds after the designated runtime that the job is still
                allowed to be run (or ``None`` to allow the job to run no matter how late it is)
            :param bool coalesce: run once instead of many times if the scheduler determines that the
                job should be run more than once in succession
            :param int max_instances: maximum number of concurrently running instances allowed for this
                job
            :param datetime next_run_time: when to first run the job, regardless of the trigger (pass
                ``None`` to add the job as paused)
            :param str|unicode jobstore: alias of the job store to store the job in
            :param str|unicode executor: alias of the executor to run the job with
            :param bool replace_existing: ``True`` to replace an existing job with the same ``id``
                (but retain the number of runs from the existing one)
            :return: Job
            """

.. code-block:: python

    def add_nonblocking_job(
        self, func: Callable, trigger: str = None, args: Union[list, tuple] = None,
        kwargs: dict = None, id: str = None, name: str = None,
        misfire_grace_time: int = undefined, coalesce: bool = undefined, max_instances: int = undefined,
        next_run_time: datetime = undefined, jobstore: str = 'default', executor: str = 'default',
        replace_existing: bool = False, **trigger_args: Any) -> Job:
            """
            Just an apscheduler add job wrapper.
            :param func: callable (or a textual reference to one) to run at the given time
            :param str|apscheduler.triggers.base.BaseTrigger trigger: trigger that determines when
                ``func`` is called
            :param list|tuple args: list of positional arguments to call func with
            :param dict kwargs: dict of keyword arguments to call func with
            :param str|unicode id: explicit identifier for the job (for modifying it later)
            :param str|unicode name: textual description of the job
            :param int misfire_grace_time: seconds after the designated runtime that the job is still
                allowed to be run (or ``None`` to allow the job to run no matter how late it is)
            :param bool coalesce: run once instead of many times if the scheduler determines that the
                job should be run more than once in succession
            :param int max_instances: maximum number of concurrently running instances allowed for this
                job
            :param datetime next_run_time: when to first run the job, regardless of the trigger (pass
                ``None`` to add the job as paused)
            :param str|unicode jobstore: alias of the job store to store the job in
            :param str|unicode executor: alias of the executor to run the job with
            :param bool replace_existing: ``True`` to replace an existing job with the same ``id``
                (but retain the number of runs from the existing one)
            :return: Job
            """

.. code-block:: python

     def get_blocking_scheduler(self) -> BlockingScheduler:
        """
        Return self blocking scheduler
        :return: BlockingScheduler
        """

.. code-block:: python

        def get_nonblocking_scheduler(self) -> BackgroundScheduler:
            """
            Return self background scheduler
            :return: BackgroundScheduler
            """

.. code-block:: python

    def start_block_scheduler(self, *args: Any, **kwargs: Any) -> None:
        """
        Start blocking scheduler
        :return: None
        """

.. code-block:: python

    def start_nonblocking_scheduler(self, *args: Any, **kwargs: Any) -> None:
        """
        Start background scheduler
        :return: None
        """

.. code-block:: python

    def start_all_scheduler(self, *args: Any, **kwargs: Any) -> None:
        """
        Start background and blocking scheduler
        :return: None
        """

.. code-block:: python

    def add_interval_blocking_secondly(
            self, function: Callable, id: str = None, args: Union[list, tuple] = None,
            kwargs: dict = None, seconds: int = 1, **trigger_args: Any) -> Job:

.. code-block:: python

        def add_interval_blocking_minutely(
            self, function: Callable, id: str = None, args: Union[list, tuple] = None,
            kwargs: dict = None, minutes: int = 1, **trigger_args: Any) -> Job:

.. code-block:: python

    def add_interval_blocking_hourly(
            self, function: Callable, id: str = None, args: Union[list, tuple] = None,
            kwargs: dict = None, hours: int = 1, **trigger_args: Any) -> Job:

.. code-block:: python

    def add_interval_blocking_daily(
            self, function: Callable, id: str = None, args: Union[list, tuple] = None,
            kwargs: dict = None, days: int = 1, **trigger_args: Any) -> Job:

.. code-block:: python

    def add_interval_blocking_weekly(
            self, function: Callable, id: str = None, args: Union[list, tuple] = None,
            kwargs: dict = None, weeks: int = 1, **trigger_args: Any) -> Job:

.. code-block:: python

    def add_interval_nonblocking_secondly(
            self, function: Callable, id: str = None, args: list = None,
            kwargs: dict = None, seconds: int = 1, **trigger_args: Any) -> Job:

.. code-block:: python

    def add_interval_nonblocking_minutely(
            self, function: Callable, id: str = None, args: list = None,
            kwargs: dict = None, minutes: int = 1, **trigger_args: Any) -> Job:

.. code-block:: python

    def add_interval_nonblocking_hourly(
            self, function: Callable, id: str = None, args: Union[list, tuple] = None,
            kwargs: dict = None, hours: int = 1, **trigger_args: Any) -> Job:

.. code-block:: python

    def add_interval_nonblocking_daily(
            self, function: Callable, id: str = None, args: Union[list, tuple] = None,
            kwargs: dict = None, days: int = 1, **trigger_args: Any) -> Job:

.. code-block:: python

    def add_interval_nonblocking_weekly(
            self, function: Callable, id: str = None, args: Union[list, tuple] = None,
            kwargs: dict = None, weeks: int = 1, **trigger_args: Any) -> Job:

.. code-block:: python

    def add_cron_blocking(
        self, function: Callable, id: str = None, **trigger_args: Any) -> Job:

.. code-block:: python

    def add_cron_nonblocking(
            self, function: Callable, id: str = None, **trigger_args: Any) -> Job:

.. code-block:: python

    def remove_blocking_job(self, id: str, jobstore: str = 'default') -> Any:

.. code-block:: python

    def remove_nonblocking_job(self, id: str, jobstore: str = 'default') -> Any:

.. code-block:: python

    def shutdown_blocking_scheduler(self, wait: bool = False) -> None:

.. code-block:: python

        def shutdown_nonblocking_scheduler(self, wait: bool = False) -> None:
